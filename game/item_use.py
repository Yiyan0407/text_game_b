"""探索/战斗中共用的物品使用机械结算。"""

from __future__ import annotations

from game.dice import roll
from game.item_kinds import infer_gear_slot, is_healing_item
from game.models import Character


def resolve_use_item(character: Character, item_refs: list[str]) -> list[str]:
    if not item_refs:
        return ["未指定要使用的物品。"]

    item_ref = item_refs[0].strip()
    if not item_ref:
        return ["未指定要使用的物品。"]

    if not character.has_inventory_item(item_ref):
        return [f"背包中没有：{item_ref}"]

    target = character.find_inventory_item(item_ref)
    if target is None:
        return [f"背包中没有：{item_ref}"]

    if target.kind == "document":
        return [
            f"查阅：{target.format_detail()}",
            "具体内容由 KP 叙事描述；物品仍保留在背包。",
        ]

    if target.kind == "durable":
        if character.is_item_active(target.name):
            character.clear_active_gear_item(target.name)
            return [f"收起：{target.name}"]
        message = character.set_active_gear(target)
        return [message, "具体效果由 KP 叙事描述。"]

    ok, consume_msg = character.consume_inventory_quantity(item_ref, 1)
    if not ok:
        return [f"使用失败：{consume_msg}"]

    label = target.name
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

    return events
