"""StatForge 效果校验与封顶。"""

from __future__ import annotations

from game.effects import EntityEffects

WORLD_SP_CAP: dict[str, int] = {
    "fantasy": 15,
    "modern": 12,
    "cyberpunk": 30,
    "xianxia": 25,
    "": 30,
}

WORLD_DAMAGE_HINT: dict[str, str] = {
    "modern": "1d10",
    "cyberpunk": "2d10+1d8",
    "xianxia": "2d8+1d8",
    "fantasy": "1d8",
}


WORLD_HEAL_HINT: dict[str, str] = {
    "modern": "2d4+2",
    "cyberpunk": "2d6+2",
    "xianxia": "2d8+2",
    "fantasy": "2d4+2",
}


def _validate_dice_field(value: str, *, fallback: str) -> str:
    if not value:
        return ""
    from game.dice import roll_damage

    try:
        roll_damage(value)
        return value
    except ValueError:
        return fallback


def validate_effects(effects: EntityEffects, *, world_id: str = "") -> EntityEffects:
    data = effects.model_copy(deep=True)
    cap = WORLD_SP_CAP.get(world_id, 30)

    if data.sp_max > cap:
        data.sp_max = cap
    if data.sp > data.sp_max:
        data.sp = data.sp_max

    data.ac_bonus = max(-2, min(5, data.ac_bonus))
    data.max_hp_bonus = max(0, min(20, data.max_hp_bonus))
    data.attack_bonus = max(-2, min(10, data.attack_bonus))

    if data.attack_damage:
        data.attack_damage = _validate_dice_field(
            data.attack_damage,
            fallback=WORLD_DAMAGE_HINT.get(world_id, "1d6"),
        )

    if data.use_damage:
        data.use_damage = _validate_dice_field(
            data.use_damage,
            fallback=WORLD_DAMAGE_HINT.get(world_id, "2d6"),
        )

    if data.heal_dice:
        data.heal_dice = _validate_dice_field(
            data.heal_dice,
            fallback=WORLD_HEAL_HINT.get(world_id, "2d4+2"),
        )

    if data.sp_max > 0 and data.sp <= 0:
        data.sp = data.sp_max

    return data
