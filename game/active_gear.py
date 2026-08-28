"""当前持用装备（照明/工具/武器）。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from game.item_kinds import GearSlot, gear_slot_status


class ActiveGearEntry(BaseModel):
    slot: GearSlot
    item_name: str = Field(min_length=1)

    @field_validator("item_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        return value.strip()

    def format_line(self) -> str:
        return f"{self.item_name}（{gear_slot_status(self.slot)}）"


def normalize_active_gear(value) -> list[ActiveGearEntry]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("active_gear must be a list")
    entries: list[ActiveGearEntry] = []
    for entry in value:
        if isinstance(entry, ActiveGearEntry):
            entries.append(entry)
        elif isinstance(entry, dict):
            entries.append(ActiveGearEntry.model_validate(entry))
        elif isinstance(entry, str):
            text = entry.strip()
            if text:
                entries.append(ActiveGearEntry(slot="tool", item_name=text))
        else:
            raise TypeError(f"unsupported active_gear entry: {entry!r}")
    return _dedupe_slots(entries)


def _dedupe_slots(entries: list[ActiveGearEntry]) -> list[ActiveGearEntry]:
    by_slot: dict[str, ActiveGearEntry] = {}
    for entry in entries:
        by_slot[entry.slot] = entry
    order: tuple[GearSlot, ...] = ("light", "tool", "weapon")
    return [by_slot[slot] for slot in order if slot in by_slot]
