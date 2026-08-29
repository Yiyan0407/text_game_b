from game.kp_scan_parse import (
    build_implant_registration_patch,
    extract_kp_scan_modules,
    is_implant_audit_context,
    merge_implant_fallback_patch,
    missing_implant_modules,
)
from game.models import Character, GameState
from game.results import StatePatch
from game.state_patch import apply_state_patch


KP_SCAN = """
[义体自检启动中...]

神经突触增强器——信号延迟0.003毫秒，正常。
视网膜投影模块——分辨率与夜视功能，正常。
耳后义体接口——量子纠缠通信器已识别，信号稳定，待激活。
反应增强肌纤维——张力校准完成，峰值输出98.7%。
骨骼强化涂层——无裂痕，结构完整。

[扫描完成：全系统状态良好]
"""


def test_extract_kp_scan_modules_skips_interface_lines():
    modules = extract_kp_scan_modules(KP_SCAN)
    assert modules == [
        "神经突触增强器",
        "视网膜投影模块",
        "反应增强肌纤维",
        "骨骼强化涂层",
    ]


def test_is_implant_audit_context_from_user_and_kp():
    assert is_implant_audit_context("启动全身义体并进行自检", "")
    assert is_implant_audit_context("", "[义体自检启动中...]")
    assert not is_implant_audit_context("这里天气怎么样", "雨还在下。")


def test_missing_implant_modules():
    character = Character(name="里昂")
    missing = missing_implant_modules(character, KP_SCAN)
    assert len(missing) == 4


def test_merge_implant_fallback_registers_scan_modules():
    character = Character(name="里昂")
    patch = merge_implant_fallback_patch(
        StatePatch(),
        character,
        KP_SCAN,
        "小爱同学，全面扫描全身义体，并登记入系统",
    )
    assert len(patch.inventory) == 4
    assert len(patch.equipment) == 4
    assert all(entry.slot == "body" for entry in patch.equipment)


def test_implant_fallback_applies_with_inventory_sync():
    character = Character(name="里昂")
    patch = merge_implant_fallback_patch(
        StatePatch(),
        character,
        KP_SCAN,
        "全面扫描义体并登记",
    )
    events = apply_state_patch(
        patch,
        character,
        GameState(),
        inventory_sync=True,
    )
    assert character.has_inventory_item("神经突触增强器")
    assert character.is_item_equipped("骨骼强化涂层")
    assert any("获得" in event for event in events)
    assert not character.has_inventory_item("耳后义体接口")


def test_build_implant_registration_patch_kind_and_description():
    patch = build_implant_registration_patch(["神经突触增强器"])
    assert patch.inventory[0].kind == "durable"
    assert patch.inventory[0].description == "已植入"
    assert patch.equipment[0].slot == "body"
