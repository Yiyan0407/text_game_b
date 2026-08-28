"""Audit Streamlit widget keys for common footguns."""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = [ROOT / "ui", ROOT / "app.py"]


def _paths() -> list[Path]:
    out: list[Path] = []
    for item in SCAN:
        if item.is_file():
            out.append(item)
        else:
            out.extend(item.rglob("*.py"))
    return out


def _const_map(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for m in re.finditer(r'^([A-Z][A-Z0-9_]*)\s*=\s*"([^"]+)"', text, re.M):
        mapping[m.group(1)] = m.group(1)
        mapping.setdefault(m.group(1) + "_val", m.group(2))
    for m in re.finditer(r"^([A-Z][A-Z0-9_]*)\s*=\s*'([^']+)'", text, re.M):
        mapping[m.group(1)] = m.group(1)
    return mapping


def _resolve_key(node: ast.AST | None, consts: dict[str, str]) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in consts:
        # look up string value in file
        return None
    if isinstance(node, ast.Name):
        return f"${node.id}"  # symbolic
    if isinstance(node, ast.JoinedStr):
        return None  # f-string dynamic
    return None


def _widget_keys_in_file(path: Path) -> dict[str, list[int]]:
    text = path.read_text(encoding="utf-8")
    consts = _const_map(text)
    # resolve const string values
    resolved: dict[str, str] = {}
    for m in re.finditer(r'^([A-Z][A-Z0-9_]*)\s*=\s*"([^"]+)"', text, re.M):
        resolved[m.group(1)] = m.group(2)
    for m in re.finditer(r"^([A-Z][A-Z0-9_]*)\s*=\s*'([^']+)'", text, re.M):
        resolved[m.group(1)] = m.group(2)

    keys: dict[str, list[int]] = defaultdict(list)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return keys

    widget_methods = {
        "button", "radio", "checkbox", "selectbox", "text_input", "text_area",
        "chat_input", "data_editor", "slider", "number_input", "multiselect",
        "download_button", "toggle",
    }

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in widget_methods
            and isinstance(func.value, ast.Name)
            and func.value.id == "st"
        ):
            continue
        for kw in node.keywords:
            if kw.arg != "key":
                continue
            key = _resolve_key(kw.value, consts)
            if key is None and isinstance(kw.value, ast.Name):
                key = resolved.get(kw.value.id, f"${kw.value.id}")
            if key:
                keys[key].append(node.lineno)
    return keys


def _find_render_call_chains() -> list[tuple[str, str]]:
    """Heuristic: functions that call other render_* and both may emit widgets."""
    chains: list[tuple[str, str]] = []
    for path in _paths():
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("render_"):
                continue
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id.startswith("render_")
                    and sub.func.id != node.name
                ):
                    chains.append((f"{rel}:{node.name}", sub.func.id))
    return chains


def main() -> int:
    static_keys: dict[str, list[str]] = defaultdict(list)
    symbolic_keys: dict[str, list[str]] = defaultdict(list)

    for path in _paths():
        rel = str(path.relative_to(ROOT))
        for key, lines in _widget_keys_in_file(path).items():
            target = symbolic_keys if key.startswith("$") else static_keys
            for line in lines:
                target[key].append(f"{rel}:{line}")

    print("=== Static widget keys used multiple times in SAME file (likely bug) ===")
    dup_file = {
        k: v for k, v in static_keys.items() if len(v) > 1 and len(set(v)) > 1
    }
    if not dup_file:
        print("(none)")
    for key, locs in sorted(dup_file.items()):
        print(f"  {key}:")
        for loc in locs:
            print(f"    - {loc}")

    print("\n=== Static widget keys shared across files (check same-page renders) ===")
    cross = {k: v for k, v in static_keys.items() if len({x.split(':')[0] for x in v}) > 1}
    if not cross:
        print("(none)")
    for key, locs in sorted(cross.items()):
        print(f"  {key}:")
        for loc in locs:
            print(f"    - {loc}")

    print("\n=== render_* call chains (parent may duplicate child widgets) ===")
    chains = _find_render_call_chains()
    if not chains:
        print("(none)")
    for parent, child in chains:
        print(f"  {parent} -> {child}()")

    # session_state vs button
    print("\n=== Button key / session_state write conflicts ===")
    button_conflicts = 0
    for path in _paths():
        text = path.read_text(encoding="utf-8")
        keys_map = _widget_keys_in_file(path)
        for m in re.finditer(r'st\.session_state\[["\']([^"\']+)["\']\]\s*=', text):
            k = m.group(1)
            if k in keys_map and "button" in text:  # rough
                line = text[: m.start()].count("\n") + 1
                print(f"  {k}: {path.relative_to(ROOT)}:{line}")
                button_conflicts += 1
    if not button_conflicts:
        print("(none)")

    return 1 if dup_file else 0


if __name__ == "__main__":
    raise SystemExit(main())
