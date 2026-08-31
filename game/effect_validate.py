"""StatForge 效果校验与封顶。"""

from __future__ import annotations

from game.effects import EntityEffects


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

    if data.sp_max > 0 and data.sp > data.sp_max:
        data.sp = data.sp_max

    data.ac_bonus = max(-5, min(5, data.ac_bonus))
    data.max_hp_bonus = max(-15, min(20, data.max_hp_bonus))
    data.attack_bonus = max(-2, min(10, data.attack_bonus))
    data.check_bonus = max(-4, min(4, data.check_bonus))

    if data.attack_damage:
        data.attack_damage = _validate_dice_field(data.attack_damage)

    if data.use_damage:
        data.use_damage = _validate_dice_field(data.use_damage)

    if data.heal_dice:
        data.heal_dice = _validate_dice_field(data.heal_dice)

    from game.models import ABILITY_FIELDS

    cleaned_related: list[str] = []
    for entry in data.related_abilities:
        key = str(entry).strip().lower()
        if key in ABILITY_FIELDS or key in ("all", "任意", "全部"):
            cleaned_related.append(key if key in ABILITY_FIELDS else "all")
    data.related_abilities = cleaned_related

    if data.sp_max > 0 and data.sp <= 0:
        data.sp = data.sp_max

    return data
