"""探索/战斗中共用的物品使用机械结算。"""

from __future__ import annotations

from game.dice import roll
from game.models import Character

_HEALING_KEYWORDS = (
    "治疗",
    "回复",
    "恢复",
    "医疗",
    "绷带",
    "急救",
    "药水",
    "药瓶",
    "药丸",
    "药片",
    "丹药",
    "灵丹",
    "potions",
    "potion",
    "healing",
)


def is_healing_item(item_ref: str) -> bool:
    text = item_ref.strip().lower()
    if not text:
        return False
    return any(keyword in text for keyword in _HEALING_KEYWORDS)


def resolve_use_item(character: Character, item_refs: list[str]) -> list[str]:
    if not item_refs:
        return ["未指定要使用的物品。"]

    item_ref = item_refs[0].strip()
    if not item_ref:
        return ["未指定要使用的物品。"]

    if not character.has_inventory_item(item_ref):
        return [f"背包中没有：{item_ref}"]

    ok, consume_msg = character.consume_inventory_quantity(item_ref, 1)
    if not ok:
        return [f"使用失败：{consume_msg}"]

    target = character.find_inventory_item(item_ref)
    label = target.name if target else item_ref
    events = [f"使用：{label}（{consume_msg}）"]

    if is_healing_item(item_ref):
        heal_roll = roll("2d4+2")
        healed = heal_roll.total
        before = character.hp
        character.hp = min(character.max_hp, character.hp + healed)
        actual = character.hp - before
        events.append(
            f"🎲 治疗 {heal_roll.describe()} = {healed} HP，"
            f"恢复 {actual} 点生命（{character.hp}/{character.max_hp}）"
        )
    else:
        events.append("具体效果由 KP 叙事描述。")

    return events
