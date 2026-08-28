"""战斗中物品使用的动作成本判定。"""

from __future__ import annotations

from game.item_kinds import infer_gear_slot, is_healing_item
from game.models import Character


def combat_use_item_cost(character: Character, item_ref: str) -> str:
    """返回战斗中使用物品的动作成本：bonus / main / free。"""
    target = character.find_inventory_item(item_ref)
    if target is None:
        return "bonus"

    if target.kind == "document":
        return "main"

    if target.kind == "consumable" or is_healing_item(item_ref):
        return "bonus"

    if target.kind == "durable":
        slot = infer_gear_slot(target.name, target.kind)
        if slot in ("weapon", "light", "tool"):
            return "free"
        return "main"

    return "bonus"
