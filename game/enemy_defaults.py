"""敌人默认战斗参数（按世界观）。"""

from __future__ import annotations

from game.models import CombatEnemy

DEFAULT_ATTACK_DAMAGE: dict[str, str] = {
    "modern": "1d6",
    "cyberpunk": "2d8",
    "xianxia": "1d8",
    "fantasy": "1d6",
}

DEFAULT_ENEMY_SP: dict[str, int] = {
    "modern": 0,
    "cyberpunk": 8,
    "xianxia": 6,
    "fantasy": 0,
}


def default_attack_damage(world_id: str) -> str:
    return DEFAULT_ATTACK_DAMAGE.get(world_id, "1d6")


def default_enemy_sp(world_id: str) -> int:
    return DEFAULT_ENEMY_SP.get(world_id, 0)


def apply_world_defaults(enemy: CombatEnemy, world_id: str) -> CombatEnemy:
    if not enemy.attack_damage.strip() or enemy.attack_damage == "1d6":
        enemy.attack_damage = default_attack_damage(world_id)
        enemy.damage_notation = enemy.attack_damage
    if enemy.sp_max <= 0 and enemy.sp <= 0 and default_enemy_sp(world_id) > 0:
        sp = default_enemy_sp(world_id)
        enemy.sp = sp
        enemy.sp_max = sp
    return enemy
