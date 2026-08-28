"""战斗距离（米）与武器射程。"""

from __future__ import annotations

from game.weapon_combat import WeaponProfile

MELEE_REACH_M = 2
PISTOL_NORMAL_M = 30
PISTOL_MAX_M = 50
RIFLE_NORMAL_M = 80
RIFLE_MAX_M = 150
DEFAULT_START_DISTANCE_M = 10
LONG_RANGE_PENALTY = 2


def movement_speed_for(character) -> int:
    """每回合移动力（米），对标 D&D 30 尺 ≈ 9 米，略受敏捷影响。"""
    return max(6, 9 + character.modifier("dex"))


def weapon_range_m(profile: WeaponProfile) -> tuple[int, int, int]:
    """返回 (最小射程, 正常最大射程, 极限最大射程) 单位米。"""
    if profile.label == "徒手" or profile.label.startswith("徒手（"):
        return 0, MELEE_REACH_M, MELEE_REACH_M
    if profile.use_dex and profile.damage_notation == "1d10":
        return 2, PISTOL_NORMAL_M, PISTOL_MAX_M
    if profile.damage_notation == "1d8":
        return 0, MELEE_REACH_M, 3
    return 0, MELEE_REACH_M, MELEE_REACH_M


def attack_range_status(distance_m: int, profile: WeaponProfile) -> tuple[bool, int, str]:
    """是否可攻击、命中减值、说明。"""
    _min_r, normal_max, hard_max = weapon_range_m(profile)
    if distance_m > hard_max:
        return False, 0, f"超出射程（{distance_m}m > {hard_max}m）"
    penalty = 0
    note = "正常射程"
    if distance_m > normal_max:
        penalty = LONG_RANGE_PENALTY
        note = f"远距射击（>{normal_max}m，命中 -{penalty}）"
    elif profile.use_dex and distance_m < _min_r:
        return False, 0, f"距离过近（{distance_m}m < {_min_r}m）"
    return True, penalty, note


def format_distance_line(enemy_name: str, distance_m: int) -> str:
    return f"- {enemy_name}：{distance_m}m"
