from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_STACK_ITEM_RE = re.compile(r"^(.+?)（(\d+)(.+?)）$")
_QUALIFIER_RE = re.compile(r"^(.+?)（(.+?)）$")
_CN_ONE_PREFIXES = ("一", "壹", "单")


class InventoryItem(BaseModel):
    name: str
    quantity: int = Field(default=1, ge=1)
    unit: str = "个"

    @field_validator("name", "unit")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    def display(self) -> str:
        if self.quantity == 1 and self.unit == "个":
            return self.name
        return f"{self.name}（{self.quantity}{self.unit}）"

    @classmethod
    def parse(cls, text: str) -> InventoryItem:
        raw = text.strip()
        if not raw:
            raise ValueError("物品名称不能为空")

        match = _STACK_ITEM_RE.match(raw)
        if match:
            return cls(
                name=match.group(1).strip(),
                quantity=int(match.group(2)),
                unit=match.group(3).strip() or "个",
            )

        match = _QUALIFIER_RE.match(raw)
        if match:
            name = match.group(1).strip()
            unit_part = match.group(2).strip()
            quantity, unit = _parse_unit_qualifier(unit_part)
            return cls(name=name, quantity=quantity, unit=unit or "个")

        return cls(name=raw, quantity=1, unit="个")

    def matches(self, item_ref: str) -> bool:
        ref = item_ref.strip()
        if not ref:
            return False
        if ref == self.display() or ref == self.name:
            return True
        ref_norm = _normalize_name(ref)
        name_norm = _normalize_name(self.name)
        display_norm = _normalize_name(self.display())
        return (
            ref_norm == name_norm
            or ref_norm in name_norm
            or name_norm in ref_norm
            or ref_norm == display_norm
            or ref_norm in display_norm
            or display_norm in ref_norm
        )


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())


def _parse_unit_qualifier(unit_part: str) -> tuple[int, str]:
    cleaned = unit_part.strip()
    if not cleaned:
        return 1, "个"
    if cleaned.isdigit():
        return int(cleaned), "个"
    for prefix in _CN_ONE_PREFIXES:
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
            return 1, cleaned[len(prefix) :] or "个"
    return 1, cleaned


def normalize_inventory_list(value) -> list[InventoryItem]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("inventory must be a list")
    items: list[InventoryItem] = []
    for entry in value:
        if isinstance(entry, InventoryItem):
            items.append(entry)
        elif isinstance(entry, str):
            items.append(InventoryItem.parse(entry))
        elif isinstance(entry, dict):
            items.append(InventoryItem.model_validate(entry))
        else:
            raise TypeError(f"unsupported inventory entry: {entry!r}")
    return items


def merge_inventory_items(items: list[InventoryItem]) -> list[InventoryItem]:
    merged: dict[tuple[str, str], InventoryItem] = {}
    for item in items:
        key = (item.name, item.unit)
        if key in merged:
            merged[key].quantity += item.quantity
        else:
            merged[key] = item.model_copy()
    return list(merged.values())
