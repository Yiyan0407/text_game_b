from game.equipment import EquipmentEntry, coerce_equipment_slot
from game.models import Character, GameState
from game.results import EquipmentPatch, InventoryPatch, StatePatch
from game.state_patch import apply_state_patch


def test_coerce_legacy_slots():
    assert coerce_equipment_slot("weapon") == "hand"
    assert coerce_equipment_slot("implant") == "body"
    assert coerce_equipment_slot("head") == "body"


def test_equip_item_requires_slot():
    character = Character(name="测试")
    character.add_inventory_item("军用义眼", quantity=1, unit="套", description="战术义眼")
    ok, message = character.equip_item("军用义眼")
    assert not ok
    assert "槽位" in message


def test_equip_item_with_explicit_slot():
    character = Character(name="测试")
    character.add_inventory_item("军用义眼", quantity=1, unit="套", description="战术义眼")
    ok, message = character.equip_item("军用义眼", slot="body")
    assert ok
    assert "装备" in message
    assert character.is_item_equipped("军用义眼")
    assert "身体" in character.format_equipment()


def test_explicit_slot_equip_without_keywords():
    character = Character(name="测试")
    game_state = GameState()
    patch = StatePatch(
        inventory=[
            InventoryPatch(
                action="add",
                item="未知模块",
                quantity=1,
                unit="套",
                kind="durable",
                description="未知植入模块",
            ),
        ],
        equipment=[
            EquipmentPatch(action="equip", item="未知模块", slot="body"),
        ],
    )
    apply_state_patch(patch, character, game_state)
    entry = character.find_equipment_entry(item_name="未知模块")
    assert entry is not None
    assert entry.slot == "body"


def test_multiple_hand_and_body_items():
    character = Character(name="测试")
    character.add_inventory_item("短剑", quantity=1, unit="把", description="精钢短剑")
    character.add_inventory_item("手枪", quantity=1, unit="把", description="格洛克手枪")
    character.add_inventory_item("斯安威斯坦", quantity=1, unit="套", description="时间减速义体")
    character.add_inventory_item("黑客操作系统", quantity=1, unit="套", description="网络入侵套件")
    character.equip_item("短剑", slot="hand")
    character.equip_item("手枪", slot="hand")
    character.equip_item("斯安威斯坦", slot="body")
    character.equip_item("黑客操作系统", slot="body")
    hands = [entry for entry in character.equipment if entry.slot == "hand"]
    bodies = [entry for entry in character.equipment if entry.slot == "body"]
    assert len(hands) == 2
    assert len(bodies) == 2


def test_apply_state_patch_equips_after_inventory_add():
    character = Character(name="测试")
    game_state = GameState()
    patch = StatePatch(
        inventory=[
            InventoryPatch(
                action="add",
                item="战术夹克",
                quantity=1,
                unit="件",
                description="防弹夹克",
            ),
        ],
        equipment=[
            EquipmentPatch(action="equip", item="战术夹克", slot="body"),
        ],
    )
    events = apply_state_patch(patch, character, game_state)
    assert character.has_inventory_item("战术夹克")
    assert character.is_item_equipped("战术夹克")
    assert any("装备" in event for event in events)


def test_unequip_keeps_item_in_inventory():
    character = Character(name="测试")
    character.add_inventory_item("短剑", quantity=1, unit="把", description="精钢短剑")
    character.equip_item("短剑", slot="hand")
    ok, message = character.unequip_item("短剑")
    assert ok
    assert "回背包" in message
    assert character.has_inventory_item("短剑")
    assert not character.is_item_equipped("短剑")


def test_unequip_does_not_restore_missing_inventory():
    character = Character(name="测试")
    character.equipment.append(EquipmentEntry(slot="hand", item_name="幽灵枪"))
    ok, message = character.unequip_item("幽灵枪")
    assert ok
    assert not character.has_inventory_item("幽灵枪")


def test_apply_state_patch_blocks_remove_on_unequip():
    character = Character(name="测试")
    character.add_inventory_item("短剑", quantity=1, unit="把", description="精钢短剑")
    character.equip_item("短剑", slot="hand")
    game_state = GameState()
    patch = StatePatch(
        equipment=[EquipmentPatch(action="unequip", item="短剑")],
        inventory=[InventoryPatch(action="remove", item="短剑", quantity=1)],
    )
    events = apply_state_patch(patch, character, game_state)
    assert character.has_inventory_item("短剑")
    assert not character.is_item_equipped("短剑")
    assert any("跳过移除" in event for event in events)


def test_apply_state_patch_removes_duplicate_while_equipped():
    character = Character(name="测试")
    character.add_inventory_item(
        "分子切割器", quantity=2, unit="枚", description="切割器", kind="durable"
    )
    character.equip_item("分子切割器", slot="hand")
    game_state = GameState()
    patch = StatePatch(
        inventory=[InventoryPatch(action="remove", item="分子切割器", quantity=1, unit="枚")],
    )
    events = apply_state_patch(patch, character, game_state)
    assert character.is_item_equipped("分子切割器")
    assert character.find_inventory_item("分子切割器").quantity == 1
    assert any("背包更新" in event for event in events)


def test_apply_state_patch_unequip_remove_re_equip_order():
    character = Character(name="测试")
    character.add_inventory_item(
        "分子切割器", quantity=2, unit="枚", description="切割器", kind="durable"
    )
    character.equip_item("分子切割器", slot="hand")
    game_state = GameState()
    patch = StatePatch(
        equipment=[
            EquipmentPatch(action="unequip", item="分子切割器", slot="hand"),
            EquipmentPatch(action="equip", item="分子切割器", slot="hand"),
        ],
        inventory=[InventoryPatch(action="remove", item="分子切割器", quantity=1, unit="枚")],
    )
    events = apply_state_patch(patch, character, game_state)
    assert character.is_item_equipped("分子切割器")
    assert character.find_inventory_item("分子切割器").quantity == 1
    assert not any("跳过移除" in event for event in events)
    assert any("装备" in event for event in events)


def test_no_auto_equip_without_equipment_patch():
    character = Character(name="测试")
    game_state = GameState()
    patch = StatePatch(
        inventory=[
            InventoryPatch(
                action="add",
                item="军用义眼",
                quantity=1,
                unit="套",
                description="已植入完成",
            ),
        ],
    )
    apply_state_patch(patch, character, game_state, user_input="好的")
    assert character.has_inventory_item("军用义眼")
    assert not character.is_item_equipped("军用义眼")


def test_remove_inventory_clears_equipment():
    character = Character(name="测试")
    character.add_inventory_item("短剑", quantity=1, unit="把", description="精钢短剑")
    character.equip_item("短剑", slot="hand")
    character.remove_inventory_item("短剑")
    assert not character.equipment
