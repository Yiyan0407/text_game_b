from game.inventory import InventoryItem
from game.item_kinds import infer_gear_slot, infer_item_kind


def test_infer_consumable_food():
    assert infer_item_kind("压缩饼干", unit="包") == "consumable"
    assert infer_item_kind("治疗药水") == "consumable"
    assert infer_item_kind("照明棒", unit="根") == "consumable"


def test_infer_durable_tools_and_light():
    assert infer_item_kind("头戴式手电筒") == "durable"
    assert infer_item_kind("军用多功能铁锹", unit="把") == "durable"


def test_infer_document():
    assert infer_item_kind("加密文档副本", unit="份") == "document"
    assert infer_item_kind("第七病房图纸副本", unit="份") == "document"
    assert infer_item_kind("周记出行名片", unit="张") == "document"


def test_inventory_item_applies_kind():
    item = InventoryItem(name="头戴式手电筒", quantity=1, unit="个")
    assert item.kind == "durable"
    assert infer_gear_slot(item.name, item.kind) == "light"


def test_gold_coin_name_is_durable_not_substring_gold():
    assert infer_item_kind("定金币", unit="枚") == "durable"
