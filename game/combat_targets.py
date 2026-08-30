"""战斗中敌人目标名解析（占位称呼 →  canonical 名称）。"""

from __future__ import annotations

import re

from game.models import CombatState
from game.text_match import resolve_fuzzy_name

_GENERIC_ENEMY_REFS = (
    "未知实体",
    "未知敌人",
    "未知",
    "敌人",
    "敌方",
    "目标",
    "怪物",
    "对手",
    "那东西",
    "这东西",
    "对方",
    "hostile",
)


def is_generic_enemy_ref(ref: str) -> bool:
    normalized = ref.strip().lower()
    if not normalized:
        return True
    return any(marker in normalized for marker in _GENERIC_ENEMY_REFS)


def resolve_living_enemy_ref(combat: CombatState | None, ref: str) -> str | None:
    """将玩家/路由中的敌人称呼解析为当前存活敌人的 canonical name。"""
    name = ref.strip()
    if not name or combat is None:
        return None
    living = combat.living_enemy_names()
    if not living:
        return None
    resolved = resolve_fuzzy_name(name, living)
    if resolved:
        return resolved
    if len(living) == 1 and is_generic_enemy_ref(name):
        return living[0]
    return None


def normalize_enemy_ref(combat: CombatState | None, ref: str) -> str:
    """解析失败时返回原字符串。"""
    resolved = resolve_living_enemy_ref(combat, ref)
    return resolved or ref.strip()


_HOLD_DISTANCE_RE = re.compile(
    r"保持\s*(\d+|[一二两三四五六七八九十]+)\s*米"
    r"|维持\s*(\d+|[一二两三四五六七八九十]+)\s*米"
    r"|间隔\s*(\d+|[一二两三四五六七八九十]+)\s*米"
    r"|(\d+|[一二两三四五六七八九十]+)\s*米距离"
)

_CN_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _parse_distance_token(token: str) -> int | None:
    token = token.strip()
    if not token:
        return None
    if token.isdigit():
        return max(0, int(token))
    if token in _CN_NUMBERS:
        return _CN_NUMBERS[token]
    if token.startswith("十") and len(token) == 1:
        return 10
    return None


def parse_hold_distance_meters(user_input: str) -> int | None:
    """「保持一米距离」等表述中的目标间距（米）。"""
    match = _HOLD_DISTANCE_RE.search(user_input.strip())
    if not match:
        return None
    for group in match.groups():
        if group:
            parsed = _parse_distance_token(group)
            if parsed is not None:
                return parsed
    return None


def effective_enemy_distance(
    combat: CombatState | None,
    enemy_ref: str,
    *,
    default: int = 10,
) -> int:
    """读取与敌人的距离；0m 为有效值，仅 None 时回退 default。"""
    if combat is None:
        return default
    dist = combat.distance_to(enemy_ref)
    if dist is None:
        return default
    return dist


def normalize_combat_enemy_refs(route, combat: CombatState) -> None:
    """统一 attack_target / move_target 为 canonical 敌人名。"""
    if route.attack_target.strip():
        route.attack_target = normalize_enemy_ref(combat, route.attack_target)
    if route.move_target.strip():
        route.move_target = normalize_enemy_ref(combat, route.move_target)
    elif route.attack_target.strip() and route.move_meters > 0:
        route.move_target = route.attack_target
