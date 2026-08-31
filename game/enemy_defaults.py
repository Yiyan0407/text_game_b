"""敌人默认战斗参数（按世界观）。"""

from __future__ import annotations

from game.models import CombatEnemy

DEFAULT_ATTACK_DAMAGE: dict[str, str] = {
    "modern": "1d6",
    "cyberpunk": "2d8",
    "scifi": "2d8",
    "post_apoc": "1d8",
    "steampunk": "1d8",
    "historical": "1d6",
    "coc": "1d4",
    "wuxia": "1d8",
    "xianxia": "1d8",
    "fantasy": "1d6",
}

def default_attack_damage(world_id: str) -> str:
    return DEFAULT_ATTACK_DAMAGE.get(world_id, "1d6")


def apply_world_defaults(enemy: CombatEnemy, world_id: str) -> CombatEnemy:
    """仅补缺失的攻击骰；SP/HP/AC 由 enemy_defs 或叙事单独设定，不按世界观一刀切。"""
    if not enemy.attack_damage.strip() or enemy.attack_damage == "1d6":
        enemy.attack_damage = default_attack_damage(world_id)
        enemy.damage_notation = enemy.attack_damage
    return enemy
