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


def _validate_dice_field(value: str) -> str:
    if not value:
        return ""
    from game.dice import roll_damage

    try:
        roll_damage(value)
        return value
    except ValueError:
        return ""


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
        data.attack_damage = _validate_dice_field(data.attack_damage)

    if data.use_damage:
        data.use_damage = _validate_dice_field(data.use_damage)

    if data.heal_dice:
        data.heal_dice = _validate_dice_field(data.heal_dice)

    if data.sp_max > 0 and data.sp <= 0:
        data.sp = data.sp_max

    return data
