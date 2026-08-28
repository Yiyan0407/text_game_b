"""玩家与 KP 的出戏沟通指令（【kp】前缀）。"""

from __future__ import annotations

import re

_KP_DIRECTIVE_RE = re.compile(r"^[\[【]\s*kp\s*[\]】]\s*", re.IGNORECASE)


def parse_kp_directive(text: str) -> str | None:
    """若输入以 【kp】 / [kp] 开头，返回去掉前缀后的正文；否则 None。"""
    normalized = text.strip()
    if not normalized:
        return None
    match = _KP_DIRECTIVE_RE.match(normalized)
    if not match:
        return None
    body = normalized[match.end() :].strip()
    return body or None


def is_kp_directive(text: str) -> bool:
    return parse_kp_directive(text) is not None
