"""物品类型与持用槽。"""

from __future__ import annotations

from typing import Literal

ItemKind = Literal["consumable", "durable", "document"]
GearSlot = Literal["light", "tool", "weapon"]

_SLOT_STATUS = {
    "light": "照明中",
    "tool": "使用中",
    "weapon": "握持中",
}


def gear_slot_status(slot: GearSlot) -> str:
    return _SLOT_STATUS.get(slot, "使用中")
