"""战斗中使用物品的动作成本判定。"""

from __future__ import annotations

from game.inventory import InventoryItem
from game.item_kinds import GearSlot, infer_gear_slot
from game.models import Character


def combat_use_item_cost(character: Character, item_ref: str) -> str:
    """返回战斗中使用物品的动作成本：bonus / main / free。"""
    target = character.find_inventory_item(item_ref)
    if target is None:
        return "bonus"

    if target.kind == "document":
        return "main"

    if target.effects and target.effects.forged and target.effects.has_use_effect():
        return "bonus"

    if target.kind == "durable":
        if _durable_use_is_free(character, target):
            return "free"
        return "main"

    if target.kind == "consumable":
        return "bonus"

    return "bonus"


def _durable_use_is_free(character: Character, item: InventoryItem) -> bool:
    if character.is_item_in_hand(item.name):
        return True
    slot = _resolve_gear_slot(item)
    return slot in ("weapon", "light", "tool")


def _resolve_gear_slot(item: InventoryItem) -> GearSlot | None:
    if item.effects:
        slot = item.effects.inferred_gear_slot()
        if slot in ("weapon", "light", "tool"):
            return slot  # type: ignore[return-value]
    return infer_gear_slot(item.name, item.kind)


def should_auto_equip_weapon_on_pickup(item: InventoryItem) -> bool:
    """战斗中拾取后是否自动装备到手持（武器）。"""
    if item.effects:
        slot = item.effects.inferred_gear_slot()
        if slot == "weapon":
            return True
    return infer_gear_slot(item.name, item.kind) == "weapon"
