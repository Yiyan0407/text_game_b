"""已装备物品：手持 / 身体 / 配件。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

EquipmentSlot = Literal["hand", "body", "accessory"]

_SLOT_ORDER: tuple[EquipmentSlot, ...] = ("hand", "body", "accessory")

SLOT_LABELS: dict[EquipmentSlot, str] = {
    "hand": "手持",
    "body": "身体",
    "accessory": "配件",
}

_LEGACY_SLOT_MAP: dict[str, EquipmentSlot] = {
    "weapon": "hand",
    "off_hand": "hand",
    "armor": "body",
    "head": "body",
    "torso": "body",
    "arms": "body",
    "legs": "body",
    "implant": "body",
    "accessory": "accessory",
}


class EquipmentEntry(BaseModel):
    slot: EquipmentSlot
    item_name: str = Field(min_length=1)

    @field_validator("slot", mode="before")
    @classmethod
    def _coerce_slot(cls, value) -> EquipmentSlot:
        return coerce_equipment_slot(str(value or ""))

    @field_validator("item_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        return value.strip()

    def format_line(self) -> str:
        return f"{self.item_name}（{SLOT_LABELS.get(self.slot, self.slot)}）"


def coerce_equipment_slot(value: str) -> EquipmentSlot:
    cleaned = value.strip().lower()
    if cleaned in _SLOT_ORDER:
        return cleaned  # type: ignore[return-value]
    if cleaned in _LEGACY_SLOT_MAP:
        return _LEGACY_SLOT_MAP[cleaned]
    return "accessory"


def normalize_equipment(value) -> list[EquipmentEntry]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("equipment must be a list")
    entries: list[EquipmentEntry] = []
    for entry in value:
        if isinstance(entry, EquipmentEntry):
            entries.append(entry)
        elif isinstance(entry, dict):
            entries.append(EquipmentEntry.model_validate(entry))
        elif isinstance(entry, str):
            text = entry.strip()
            if text:
                entries.append(EquipmentEntry(slot="accessory", item_name=text))
        else:
            raise TypeError(f"unsupported equipment entry: {entry!r}")
    return _normalize_entries(entries)


def is_valid_equipment_slot(value: str) -> bool:
    cleaned = value.strip().lower()
    return cleaned in _SLOT_ORDER or cleaned in _LEGACY_SLOT_MAP


def _normalize_entries(entries: list[EquipmentEntry]) -> list[EquipmentEntry]:
    seen: set[str] = set()
    ordered: list[EquipmentEntry] = []
    for slot in _SLOT_ORDER:
        for entry in entries:
            if entry.slot != slot:
                continue
            key = f"{entry.slot}:{entry.item_name}"
            if key in seen:
                continue
            seen.add(key)
            ordered.append(entry)
    return ordered
