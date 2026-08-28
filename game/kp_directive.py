"""玩家与 KP 的出戏沟通指令（【kp】前缀）。"""

from __future__ import annotations

import re

_KP_DIRECTIVE_RE = re.compile(r"^[\[【]\s*kp\s*[\]】]\s*", re.IGNORECASE)


def is_kp_directive(text: str) -> bool:
    """输入是否以 【kp】 / [kp] 开头（正文可为空）。"""
    normalized = text.strip()
    return bool(normalized and _KP_DIRECTIVE_RE.match(normalized))


def is_kp_meta_response(text: str) -> bool:
    """是否为 KP 出戏沟通回复（非冒险叙事）。"""
    cleaned = text.strip()
    return cleaned.startswith("**【KP 沟通】**") or cleaned.startswith("【KP 沟通】")


def parse_kp_directive(text: str) -> str | None:
    """若输入以 【kp】 / [kp] 开头，返回去掉前缀后的正文（可为空串）；否则 None。"""
    normalized = text.strip()
    if not normalized:
        return None
    match = _KP_DIRECTIVE_RE.match(normalized)
    if not match:
        return None
    return normalized[match.end() :].strip()
