"""从 KP 义体自检扫描格式解析模块名（结构化兜底，非关键词义体表）。"""

from __future__ import annotations

import re

from game.models import Character
from game.results import EquipmentPatch, InventoryPatch, StatePatch

_SCAN_LINE = re.compile(
    r"^(.{2,40}?)\s*[—–\-]{1,2}\s*(.+?)[。．]?\s*$"
)
_IMPLANT_AUDIT_USER_MARKERS = ("义体", "植入", "改造")
_IMPLANT_AUDIT_ACTION_MARKERS = ("自检", "扫描", "登记", "启动", "盘点", "检查")
_IMPLANT_AUDIT_KP_MARKERS = ("义体自检", "全面义体", "扫描完成", "全系统状态")


def is_implant_audit_context(user_input: str, kp_narrative: str) -> bool:
    """玩家或 KP 表明本轮为义体自检/登记。"""
    user = user_input.strip()
    kp = kp_narrative.strip()
    user_hit = any(m in user for m in _IMPLANT_AUDIT_USER_MARKERS) and any(
        m in user for m in _IMPLANT_AUDIT_ACTION_MARKERS
    )
    kp_hit = any(m in kp for m in _IMPLANT_AUDIT_KP_MARKERS)
    return user_hit or kp_hit


def extract_kp_scan_modules(kp_narrative: str) -> list[str]:
    """解析「模块名——状态」扫描行，去重保序。"""
    modules: list[str] = []
    seen: set[str] = set()
    for raw_line in kp_narrative.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("["):
            continue
        match = _SCAN_LINE.match(line)
        if not match:
            continue
        name = match.group(1).strip()
        status = match.group(2).strip()
        if not _is_registerable_scan_entry(name, status):
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        modules.append(name)
    return modules


def _is_registerable_scan_entry(name: str, status: str) -> bool:
    """过滤接口状态行、外接设备识别行等非独立义体模块。"""
    if name.endswith("接口"):
        return False
    if "已识别" in status:
        return False
    return True


def missing_implant_modules(character: Character, kp_narrative: str) -> list[str]:
    """KP 扫描列出但背包/装备栏尚未登记的模块。"""
    missing: list[str] = []
    for name in extract_kp_scan_modules(kp_narrative):
        if character.has_inventory_item(name) or character.is_item_equipped(name):
            continue
        missing.append(name)
    return missing


def build_implant_registration_patch(modules: list[str]) -> StatePatch:
    inventory: list[InventoryPatch] = []
    equipment: list[EquipmentPatch] = []
    for name in modules:
        inventory.append(
            InventoryPatch(
                action="add",
                item=name,
                quantity=1,
                unit="套",
                kind="durable",
                description="已植入",
            )
        )
        equipment.append(
            EquipmentPatch(action="equip", item=name, slot="body"),
        )
    return StatePatch(inventory=inventory, equipment=equipment)


def merge_implant_fallback_patch(
    patch: StatePatch,
    character: Character,
    kp_narrative: str,
    user_input: str,
) -> StatePatch:
    """ItemSync 漏登记时，用 KP 扫描结构化结果补全（最后兜底）。"""
    if not is_implant_audit_context(user_input, kp_narrative):
        return patch
    missing = missing_implant_modules(character, kp_narrative)
    if not missing:
        return patch

    fallback = build_implant_registration_patch(missing)
    existing_inv = {
        (item_name_from_patch(inv.item), inv.action)
        for inv in patch.inventory
    }
    existing_eq = {eq.item.strip() for eq in patch.equipment if eq.action == "equip"}

    merged_inv = list(patch.inventory)
    merged_eq = list(patch.equipment)
    for inv in fallback.inventory:
        key = (item_name_from_patch(inv.item), inv.action)
        if key not in existing_inv:
            merged_inv.append(inv)
    for eq in fallback.equipment:
        if eq.item.strip() not in existing_eq:
            merged_eq.append(eq)
    return StatePatch(inventory=merged_inv, equipment=merged_eq)


def item_name_from_patch(item_ref: str) -> str:
    cleaned = item_ref.strip()
    return cleaned
