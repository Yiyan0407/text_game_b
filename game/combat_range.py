"""战斗距离（米）与武器射程。"""

from __future__ import annotations

import re

from game.models import CombatEnemy
from game.weapon_combat import WeaponProfile

MELEE_REACH_M = 2
PISTOL_NORMAL_M = 30
PISTOL_MAX_M = 50
RIFLE_NORMAL_M = 80
RIFLE_MAX_M = 150
DEFAULT_START_DISTANCE_M = 10
LONG_RANGE_PENALTY = 2
MELEE_GUN_DAMAGE = "1d4"
_ENEMY_MOVE_M = 6


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


def enemy_attack_profile(enemy: CombatEnemy) -> WeaponProfile:
    return WeaponProfile(
        label=enemy.name,
        use_dex=enemy.use_dex,
        damage_notation=enemy.effective_attack_damage(),
        attack_bonus=enemy.attack_bonus,
    )


def _damage_suggests_artillery(damage: str) -> bool:
    match = re.match(r"(\d+)d(\d+)", damage.strip())
    if not match:
        return False
    count = int(match.group(1))
    return count >= 3


def enemy_weapon_range_m(enemy: CombatEnemy) -> tuple[int, int, int]:
    """敌人攻击射程（最小, 正常最大, 极限最大）。"""
    if enemy.attack_range_max_m > 0:
        normal = (
            enemy.attack_range_normal_m
            if enemy.attack_range_normal_m > 0
            else enemy.attack_range_max_m
        )
        min_r = 2 if enemy.use_dex and normal > MELEE_REACH_M else 0
        return min_r, normal, enemy.attack_range_max_m

    profile = enemy_attack_profile(enemy)
    base_min, base_normal, base_hard = weapon_range_m(profile)

    if enemy.sp_max >= 20 or _damage_suggests_artillery(enemy.effective_attack_damage()):
        return 10, RIFLE_NORMAL_M, RIFLE_MAX_M

    if enemy.start_distance_m >= 25 and base_hard <= MELEE_REACH_M:
        return 2, PISTOL_NORMAL_M, PISTOL_MAX_M

    return base_min, base_normal, base_hard


def attack_range_status(
    distance_m: int,
    profile: WeaponProfile,
    *,
    range_m: tuple[int, int, int] | None = None,
) -> tuple[bool, int, str]:
    """是否可攻击、命中减值、说明。"""
    _min_r, normal_max, hard_max = range_m or weapon_range_m(profile)
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


def enemy_attack_range_status(
    distance_m: int,
    enemy: CombatEnemy,
) -> tuple[bool, int, str]:
    profile = enemy_attack_profile(enemy)
    return attack_range_status(distance_m, profile, range_m=enemy_weapon_range_m(enemy))


def enemy_approach_meters(enemy: CombatEnemy, distance_m: int) -> int:
    """敌人本回合为进入射程可靠近的米数（0 表示无需移动）。"""
    _min_r, _normal_max, hard_max = enemy_weapon_range_m(enemy)
    if distance_m <= hard_max:
        return 0
    return min(_ENEMY_MOVE_M, distance_m - hard_max)


def enemy_retreat_meters(enemy: CombatEnemy, distance_m: int) -> int:
    """远程敌人因过近需后撤的米数（0 表示无需后撤）。"""
    min_r, _normal_max, _hard_max = enemy_weapon_range_m(enemy)
    if min_r <= 0 or distance_m >= min_r:
        return 0
    return min(_ENEMY_MOVE_M, min_r - distance_m)


def apply_ranged_melee_fallback(
    distance_m: int,
    profile: WeaponProfile,
    *,
    range_m: tuple[int, int, int] | None = None,
) -> tuple[WeaponProfile, bool]:
    """远程武器在近战距离内改用枪托/柄击（伤害降低，仍可攻击）。"""
    min_r, _normal_max, _hard_max = range_m or weapon_range_m(profile)
    if not profile.use_dex or distance_m >= min_r:
        return profile, False
    if distance_m > MELEE_REACH_M:
        return profile, False
    base_label = profile.item_name or profile.label.split("（", 1)[0].strip()
    suffix = "枪托" if profile.use_dex else "柄击"
    return (
        WeaponProfile(
            label=f"{base_label}（{suffix}）",
            use_dex=False,
            damage_notation=MELEE_GUN_DAMAGE,
            attack_bonus=profile.attack_bonus,
            item_name=profile.item_name,
        ),
        True,
    )


def format_distance_line(enemy_name: str, distance_m: int) -> str:
    return f"- {enemy_name}：{distance_m}m"
