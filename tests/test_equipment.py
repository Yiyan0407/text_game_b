from game.equipment import EquipmentEntry, coerce_equipment_slot, infer_equipment_slot
from game.models import Character, GameState
from game.results import EquipmentPatch, InventoryPatch, StatePatch
from game.state_patch import apply_state_patch


def test_infer_equipment_slot():
    assert infer_equipment_slot("格洛克手枪") == "hand"
    assert infer_equipment_slot("军用义眼") == "body"
    assert infer_equipment_slot("斯安威斯坦") == "body"
    assert infer_equipment_slot("防弹护甲") == "body"
    assert infer_equipment_slot("强化脊柱") == "body"
    assert infer_equipment_slot("幸运戒指") == "accessory"


def test_coerce_legacy_slots():
    assert coerce_equipment_slot("weapon") == "hand"
    assert coerce_equipment_slot("implant") == "body"
    assert coerce_equipment_slot("head") == "body"


def test_equip_item_from_inventory():
    character = Character(name="测试")
    character.add_inventory_item("军用义眼", quantity=1, unit="套")
    ok, message = character.equip_item("军用义眼")
    assert ok
    assert "装备" in message
    assert character.is_item_equipped("军用义眼")
    assert character.format_equipment() == "军用义眼（身体）"


def test_multiple_hand_and_body_items():
    character = Character(name="测试")
    character.add_inventory_item("短剑", quantity=1, unit="把")
    character.add_inventory_item("手枪", quantity=1, unit="把")
    character.add_inventory_item("斯安威斯坦", quantity=1, unit="套")
    character.add_inventory_item("黑客操作系统", quantity=1, unit="套")
    character.equip_item("短剑")
    character.equip_item("手枪")
    character.equip_item("斯安威斯坦")
    character.equip_item("黑客操作系统")
    hands = [entry for entry in character.equipment if entry.slot == "hand"]
    bodies = [entry for entry in character.equipment if entry.slot == "body"]
    assert len(hands) == 2
    assert len(bodies) == 2


def test_apply_state_patch_equips_after_inventory_add():
    character = Character(name="测试")
    game_state = GameState()
    patch = StatePatch(
        inventory=[
            InventoryPatch(action="add", item="战术夹克", quantity=1, unit="件"),
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
    character.add_inventory_item("短剑", quantity=1, unit="把")
    character.equip_item("短剑")
    ok, message = character.unequip_item("短剑")
    assert ok
    assert "回背包" in message
    assert character.has_inventory_item("短剑")
    assert not character.is_item_equipped("短剑")


def test_unequip_restores_missing_inventory():
    character = Character(name="测试")
    character.equipment.append(EquipmentEntry(slot="hand", item_name="幽灵枪"))
    ok, message = character.unequip_item("幽灵枪")
    assert ok
    assert character.has_inventory_item("幽灵枪")


def test_apply_state_patch_blocks_remove_on_unequip():
    character = Character(name="测试")
    character.add_inventory_item("短剑", quantity=1, unit="把")
    character.equip_item("短剑")
    game_state = GameState()
    patch = StatePatch(
        equipment=[EquipmentPatch(action="unequip", item="短剑")],
        inventory=[InventoryPatch(action="remove", item="短剑", quantity=1)],
    )
    events = apply_state_patch(patch, character, game_state)
    assert character.has_inventory_item("短剑")
    assert not character.is_item_equipped("短剑")
    assert any("跳过移除" in event for event in events)


def test_remove_inventory_clears_equipment():
    character = Character(name="测试")
    character.add_inventory_item("短剑", quantity=1, unit="把")
    character.equip_item("短剑")
    character.remove_inventory_item("短剑")
    assert not character.equipment
