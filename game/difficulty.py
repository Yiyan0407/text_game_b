"""属性检定难度（DC）的合法范围。"""

from __future__ import annotations

DC_MIN = 5
DC_MAX = 30


def clamp_dc(dc: int) -> int:
    return max(DC_MIN, min(DC_MAX, int(dc)))


def is_valid_dc(dc: int) -> bool:
    return DC_MIN <= int(dc) <= DC_MAX


def ensure_ability_check_dc(route) -> bool:
    """仅校验并 clamp 路由已给出的 DC；缺失或非法返回 False。"""
    if not route.needs_roll or route.roll_type != "ability_check":
        return True
    try:
        dc = int(route.dc)
    except (TypeError, ValueError):
        return False
    if dc <= 0:
        return False
    route.dc = clamp_dc(dc)
    return True
