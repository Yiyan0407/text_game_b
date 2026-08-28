"""物品类型与持用槽推断。"""

from __future__ import annotations

from typing import Literal

ItemKind = Literal["consumable", "durable", "document"]
GearSlot = Literal["light", "tool", "weapon"]

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

_DOCUMENT_KEYWORDS = (
    "文档",
    "图纸",
    "副本",
    "信件",
    "信函",
    "报告",
    "笔记",
    "地图",
    "草图",
    "名片",
    "证件",
    "档案",
    "卷宗",
    "手稿",
    "合同",
    "清单",
)

_CONSUMABLE_KEYWORDS = (
    "饼干",
    "口粮",
    "干粮",
    "食物",
    "照明棒",
    "荧光棒",
    "蜡烛",
)

_LIGHT_KEYWORDS = ("手电", "电筒", "头灯", "照明灯", "探照")
_TOOL_KEYWORDS = ("铁锹", "铲", "工具", "撬棍", "锤子", "绳索", "绳", "开锁器")
_WEAPON_KEYWORDS = ("剑", "刀", "枪", "弓", "弩", "棍", "匕首", "武器", "短剑", "长剑")

_SLOT_STATUS = {
    "light": "照明中",
    "tool": "使用中",
    "weapon": "握持中",
}


def is_healing_item(item_ref: str) -> bool:
    text = item_ref.strip().lower()
    if not text:
        return False
    return any(keyword in text for keyword in _HEALING_KEYWORDS)


def infer_item_kind(
    name: str,
    unit: str = "",
    description: str = "",
    *,
    explicit: str | None = None,
) -> ItemKind:
    if explicit in ("consumable", "durable", "document"):
        return explicit

    text = f"{name} {description}"
    if any(keyword in text for keyword in _DOCUMENT_KEYWORDS):
        return "document"
    if is_healing_item(name) or any(keyword in text for keyword in _CONSUMABLE_KEYWORDS):
        return "consumable"
    if unit in ("包", "瓶", "袋") and "手电" not in name:
        return "consumable"
    if unit == "根" and ("照明棒" in name or "荧光棒" in name):
        return "consumable"
    if unit == "份" and any(keyword in text for keyword in _DOCUMENT_KEYWORDS):
        return "document"
    return "durable"


def infer_gear_slot(name: str, kind: ItemKind) -> GearSlot | None:
    if kind != "durable":
        return None
    if any(keyword in name for keyword in _LIGHT_KEYWORDS):
        return "light"
    if any(keyword in name for keyword in _WEAPON_KEYWORDS):
        return "weapon"
    if any(keyword in name for keyword in _TOOL_KEYWORDS):
        return "tool"
    return "tool"


def gear_slot_status(slot: GearSlot) -> str:
    return _SLOT_STATUS.get(slot, "使用中")
