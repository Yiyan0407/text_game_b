"""创角初始行囊：按背景同步技能、背包与装备。"""

from __future__ import annotations

from dataclasses import dataclass, field

from game.equipment import coerce_equipment_slot
from game.inventory import InventoryItem
from game.models import Character
from game.skills import coerce_skill_list, sync_starter_skills


class StarterLoadoutGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class StarterInventoryEntry:
    item: str
    quantity: int = 1
    unit: str = "个"
    kind: str = "durable"
    description: str = ""


@dataclass(frozen=True)
class StarterEquipmentEntry:
    item: str
    slot: str = "hand"


@dataclass(frozen=True)
class StarterLoadout:
    skills: list[str] = field(default_factory=list)
    inventory: list[StarterInventoryEntry] = field(default_factory=list)
    equipment: list[StarterEquipmentEntry] = field(default_factory=list)


def sync_starter_loadout(character: Character, loadout: StarterLoadout) -> list[str]:
    """写入创角初始技能、物品与装备；返回简要事件行。"""
    events: list[str] = []

    if loadout.skills:
        added_skills = sync_starter_skills(character, loadout.skills)
        if added_skills:
            events.append("初始技能：" + "、".join(added_skills))

    added_items: list[str] = []
    for entry in loadout.inventory:
        name = entry.item.strip()
        if not name:
            continue
        if character.find_inventory_item(name) is not None:
            continue
        ok = character.add_inventory_item(
            InventoryItem(
                name=name,
                quantity=max(1, entry.quantity),
                unit=(entry.unit.strip() or "个"),
                description=entry.description.strip() or "背景持有，开局随身物品",
                kind=entry.kind if entry.kind in ("consumable", "durable", "document") else "durable",
            )
        )
        if ok:
            added_items.append(name)
    if added_items:
        events.append("初始物品：" + "、".join(added_items))

    equipped: list[str] = []
    for entry in loadout.equipment:
        item_name = entry.item.strip()
        if not item_name:
            continue
        slot = coerce_equipment_slot(entry.slot.strip() or "hand")
        if character.is_item_equipped(item_name):
            continue
        ok, _ = character.equip_item(item_name, slot=slot)
        if ok:
            equipped.append(item_name)
    if equipped:
        events.append("初始装备：" + "、".join(equipped))

    return events


def parse_starter_loadout_dict(data: dict) -> StarterLoadout:
    skills = coerce_skill_list(data.get("skills"))[:3]

    inventory: list[StarterInventoryEntry] = []
    for raw in data.get("inventory") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("item") or raw.get("name") or "").strip()
        if not name:
            continue
        kind = str(raw.get("kind") or "durable").strip().lower()
        if kind not in ("consumable", "durable", "document"):
            kind = "durable"
        try:
            quantity = int(raw.get("quantity") or 1)
        except (TypeError, ValueError):
            quantity = 1
        inventory.append(
            StarterInventoryEntry(
                item=name,
                quantity=max(1, quantity),
                unit=str(raw.get("unit") or "个").strip() or "个",
                kind=kind,
                description=str(raw.get("description") or "").strip(),
            )
        )
    inventory = inventory[:5]

    equipment: list[StarterEquipmentEntry] = []
    inv_names = {entry.item for entry in inventory}
    for raw in data.get("equipment") or []:
        if not isinstance(raw, dict):
            continue
        item_name = str(raw.get("item") or "").strip()
        if not item_name or item_name not in inv_names:
            continue
        equipment.append(
            StarterEquipmentEntry(
                item=item_name,
                slot=str(raw.get("slot") or "hand").strip() or "hand",
            )
        )

    return StarterLoadout(
        skills=skills,
        inventory=inventory,
        equipment=equipment[:3],
    )
