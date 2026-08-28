"""Find Streamlit widget keys that overlap with manual session_state writes."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [ROOT / "ui", ROOT / "app.py"]


def _paths() -> list[Path]:
    out: list[Path] = []
    for item in SCAN_DIRS:
        if item.is_file():
            out.append(item)
        else:
            out.extend(item.rglob("*.py"))
    return out


def _const_map(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for m in re.finditer(r'^([A-Z][A-Z0-9_]*)\s*=\s*"([^"]+)"', text, re.M):
        mapping[m.group(1)] = m.group(2)
    for m in re.finditer(r"^([A-Z][A-Z0-9_]*)\s*=\s*'([^']+)'", text, re.M):
        mapping[m.group(1)] = m.group(2)
    return mapping


def _button_keys(text: str, consts: dict[str, str]) -> set[str]:
    keys: set[str] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return keys
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_button = (
            isinstance(func, ast.Attribute)
            and func.attr == "button"
            and isinstance(func.value, ast.Name)
            and func.value.id == "st"
        )
        if not is_button:
            continue
        for kw in node.keywords:
            if kw.arg != "key":
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                keys.add(kw.value.value)
            elif isinstance(kw.value, ast.Name) and kw.value.id in consts:
                keys.add(consts[kw.value.id])
    return keys


def main() -> int:
    widget_keys: set[str] = set()
    button_keys: set[str] = set()
    session_writes: dict[str, list[str]] = {}

    for path in _paths():
        text = path.read_text(encoding="utf-8")
        consts = _const_map(text)
        button_keys |= _button_keys(text, consts)

        for m in re.finditer(r'\bkey\s*=\s*"([^"]+)"', text):
            widget_keys.add(m.group(1))
        for m in re.finditer(r"\bkey\s*=\s*'([^']+)'", text):
            widget_keys.add(m.group(1))
        for m in re.finditer(r"\bkey\s*=\s*([A-Z][A-Z0-9_]*)\b", text):
            if m.group(1) in consts:
                widget_keys.add(consts[m.group(1)])

        rel = path.relative_to(ROOT)
        for m in re.finditer(r'st\.session_state\[["\']([^"\']+)["\']\]\s*=', text):
            key = m.group(1)
            line = text[: m.start()].count("\n") + 1
            session_writes.setdefault(key, []).append(f"{rel}:{line}")
        for m in re.finditer(r"st\.session_state\.([A-Za-z_][A-Za-z0-9_]*)\s*=", text):
            key = m.group(1)
            line = text[: m.start()].count("\n") + 1
            session_writes.setdefault(key, []).append(f"{rel}:{line}")

    conflicts = {k: v for k, v in session_writes.items() if k in widget_keys}
    button_conflicts = {k: v for k, v in conflicts.items() if k in button_keys}

    print("=== Button key / session_state write conflicts (CRITICAL) ===")
    if not button_conflicts:
        print("(none)")
    for key, locs in sorted(button_conflicts.items()):
        print(f"  {key}:")
        for loc in locs:
            print(f"    - {loc}")

    other = {k: v for k, v in conflicts.items() if k not in button_keys}
    print("\n=== Other widget key / session_state writes (usually OK for radio/select) ===")
    if not other:
        print("(none)")
    for key, locs in sorted(other.items()):
        print(f"  {key}:")
        for loc in locs:
            print(f"    - {loc}")

    print(f"\nScanned {len(widget_keys)} widget keys, {len(button_keys)} button keys.")
    return 1 if button_conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
