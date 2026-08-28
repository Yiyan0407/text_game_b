from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from game.item_kinds import ItemKind, infer_item_kind
from game.effects import EntityEffects

_STACK_ITEM_RE = re.compile(r"^(.+?)（(\d+)(.+?)）$")
_QUALIFIER_RE = re.compile(r"^(.+?)（(.+?)）$")
_CN_ONE_PREFIXES = ("一", "壹", "单")
_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "壹": 1,
    "单": 1,
    "二": 2,
    "两": 2,
    "贰": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陆": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
}
_CN_TEN_MARKERS = ("十", "拾")
_VAGUE_COUNT_MARKERS = frozenset({"若干", "一些", "数个", "少量", "适量"})
_JI_UNIT_RE = re.compile(r"^几(.+)$")


class InventoryItem(BaseModel):
    name: str
    quantity: int = Field(default=1, ge=1)
    unit: str = "个"
    description: str = ""
    kind: ItemKind = "durable"
    effects: EntityEffects | None = None

    @field_validator("effects", mode="before")
    @classmethod
    def _coerce_effects(cls, value):
        return EntityEffects.coerce(value)

    @field_validator("name", "unit", "description")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _apply_kind(self) -> InventoryItem:
        object.__setattr__(
            self,
            "kind",
            infer_item_kind(self.name, self.unit, self.description),
        )
        return self

    def display(self) -> str:
        if self.quantity == 1 and self.unit == "个":
            return self.name
        return f"{self.name}（{self.quantity}{self.unit}）"

    def display_labeled(self) -> str:
        """UI 展示用：始终附带数量与单位。"""
        return f"{self.name}（{self.quantity}{self.unit}）"

    def format_detail(self) -> str:
        base = self.display_labeled()
        if self.description:
            return f"{base} — {self.description}"
        return base

    @classmethod
    def parse(cls, text: str) -> InventoryItem:
        raw = text.strip()
        if not raw:
            raise ValueError("物品名称不能为空")

        match = _STACK_ITEM_RE.match(raw)
        if match and "万" not in match.group(3):
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

    @classmethod
    def name_from_ref(cls, text: str) -> str:
        raw = text.strip()
        if not raw:
            return ""
        if "（" in raw and raw.endswith("）"):
            try:
                return cls.parse(raw).name
            except ValueError:
                return raw.split("（", 1)[0].strip()
        return raw

    def matches(self, item_ref: str) -> bool:
        ref = item_ref.strip()
        if not ref:
            return False
        if ref == self.display() or ref == self.name:
            return True

        ref_norm = _normalize_name(ref)
        name_norm = _normalize_name(self.name)
        display_norm = _normalize_name(self.display())
        if ref_norm == name_norm or ref_norm == display_norm:
            return True

        if "（" in ref and ref.endswith("）"):
            try:
                parsed = self.parse(ref)
            except ValueError:
                return False
            return parsed.name == self.name and parsed.unit == self.unit

        return False


def normalize_item_quantity_unit(quantity: int, unit: str) -> tuple[int, str]:
    cleaned = unit.strip()
    if not cleaned or cleaned in _VAGUE_COUNT_MARKERS:
        return max(1, quantity), "个" if not cleaned else "个"
    ji_match = _JI_UNIT_RE.match(cleaned)
    if ji_match:
        unit_part = ji_match.group(1).strip() or "个"
        return max(1, quantity if quantity > 1 else 3), unit_part
    return max(1, quantity), cleaned


def item_name_from_ref(text: str) -> str:
    return InventoryItem.name_from_ref(text)


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())


def _parse_chinese_quantity(text: str) -> int | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        return int(cleaned)

    if "万" in cleaned:
        left, _, right = cleaned.partition("万")
        high = _parse_chinese_quantity(left) if left else 1
        if high is None:
            return None
        low = _parse_chinese_quantity(right) if right else 0
        if right and low is None:
            return None
        return high * 10000 + low

    for ten_marker in _CN_TEN_MARKERS:
        if ten_marker in cleaned:
            left, _, right = cleaned.partition(ten_marker)
            tens = 1 if left == "" else _CN_DIGITS.get(left)
            if tens is None:
                return None
            ones = 0 if right == "" else _CN_DIGITS.get(right)
            if right and ones is None:
                return None
            return tens * 10 + ones

    if len(cleaned) == 1 and cleaned in _CN_DIGITS:
        return _CN_DIGITS[cleaned]
    return None


def _parse_unit_qualifier(unit_part: str) -> tuple[int, str]:
    cleaned = unit_part.strip()
    if not cleaned:
        return 1, "个"
    if cleaned.isdigit():
        return int(cleaned), "个"

    if cleaned in _VAGUE_COUNT_MARKERS:
        return max(1, 3), "个"

    ji_match = _JI_UNIT_RE.match(cleaned)
    if ji_match:
        unit = ji_match.group(1).strip() or "个"
        return 3, unit

    wan_match = re.match(r"^(.+万)(.+)$", cleaned)
    if wan_match:
        quantity = _parse_chinese_quantity(wan_match.group(1))
        unit = wan_match.group(2).strip()
        if quantity is not None and unit:
            return max(1, quantity), unit

    for index in range(len(cleaned), 0, -1):
        num_part = cleaned[:index]
        unit = cleaned[index:].strip()
        if not unit:
            continue
        quantity = _parse_chinese_quantity(num_part)
        if quantity is not None:
            return max(1, quantity), unit

    for prefix in _CN_ONE_PREFIXES:
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
            return 1, cleaned[len(prefix) :] or "个"
    return 1, cleaned


def _repair_inventory_item(item: InventoryItem) -> InventoryItem:
    if item.unit in _VAGUE_COUNT_MARKERS or _JI_UNIT_RE.match(item.unit or ""):
        quantity, unit = _parse_unit_qualifier(item.unit)
        return InventoryItem(
            name=item.name,
            quantity=max(item.quantity, quantity),
            unit=unit,
            description=item.description,
        )
    if item.unit.startswith("万") and len(item.unit) > 1:
        quantity, unit = _parse_unit_qualifier(f"{item.quantity}{item.unit}")
        if quantity > item.quantity and unit != item.unit:
            return InventoryItem(
                name=item.name,
                quantity=quantity,
                unit=unit,
                description=item.description,
            )
    if item.quantity != 1 or not item.unit or item.unit == "个":
        return item
    quantity, unit = _parse_unit_qualifier(item.unit)
    if quantity > 1 and unit and unit != item.unit:
        return InventoryItem(
            name=item.name,
            quantity=quantity,
            unit=unit,
            description=item.description,
        )
    return item


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
    items = [_repair_inventory_item(item) for item in items]
    return merge_inventory_items(items)


def _prefer_unit(left: str, right: str) -> str:
    if left == right:
        return left
    if left == "个":
        return right
    if right == "个":
        return left
    return left


def _merge_description(existing: InventoryItem, incoming: InventoryItem) -> None:
    incoming_desc = incoming.description.strip()
    if not incoming_desc:
        return
    if not existing.description.strip():
        existing.description = incoming_desc
    elif len(incoming_desc) > len(existing.description):
        existing.description = incoming_desc


def merge_item_stacks(existing: InventoryItem, incoming: InventoryItem) -> None:
    existing.quantity += incoming.quantity
    existing.unit = _prefer_unit(existing.unit, incoming.unit)
    _merge_description(existing, incoming)


def merge_inventory_items(items: list[InventoryItem]) -> list[InventoryItem]:
    merged: dict[str, InventoryItem] = {}
    for item in items:
        if item.name in merged:
            merge_item_stacks(merged[item.name], item)
        else:
            merged[item.name] = item.model_copy()
    return list(merged.values())
