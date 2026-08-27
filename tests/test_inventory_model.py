from game.inventory import InventoryItem, normalize_inventory_list
from game.models import Character


def test_parse_numeric_stack():
    item = InventoryItem.parse("定金币（15枚）")
    assert item.name == "定金币"
    assert item.quantity == 15
    assert item.unit == "枚"
    assert item.display() == "定金币（15枚）"


def test_parse_qualifier_stack():
    item = InventoryItem.parse("食盐（一袋）")
    assert item.name == "食盐"
    assert item.quantity == 1
    assert item.unit == "袋"
    assert item.display() == "食盐（1袋）"


def test_parse_plain_item():
    item = InventoryItem.parse("手机")
    assert item.name == "手机"
    assert item.quantity == 1
    assert item.unit == "个"
    assert item.display() == "手机"


def test_normalize_legacy_string_list():
    items = normalize_inventory_list(["旧剑", "铜板（3枚）"])
    assert items[0] == InventoryItem(name="旧剑", quantity=1, unit="个")
    assert items[1] == InventoryItem(name="铜板", quantity=3, unit="枚")


def test_parse_qualifier_stack_with_chinese_numeral():
    item = InventoryItem.parse("食盐（五袋）")
    assert item.name == "食盐"
    assert item.quantity == 5
    assert item.unit == "袋"
    assert item.display() == "食盐（5袋）"


def test_repair_malformed_unit_on_normalize():
    items = normalize_inventory_list(
        [
            InventoryItem(name="食盐", quantity=1, unit="五袋"),
            InventoryItem(name="食盐", quantity=6, unit="袋"),
        ]
    )
    assert len(items) == 1
    assert items[0].quantity == 11
    assert items[0].unit == "袋"


def test_display_labeled_always_shows_quantity():
    item = InventoryItem.parse("手机")
    assert item.display() == "手机"
    assert item.display_labeled() == "手机（1个）"

    stacked = InventoryItem.parse("定金币（15枚）")
    assert stacked.display_labeled() == "定金币（15枚）"


def test_matches_fuzzy_name():
    item = InventoryItem(name="定金币", quantity=15, unit="枚")
    assert item.matches("定金币")
    assert item.matches("定金币（15枚）")


def test_merge_same_name_different_unit():
    character = Character(name="测试", inventory=["短剑（1把）"])
    assert character.add_inventory_item("短剑", quantity=1, unit="个")
    assert len(character.inventory) == 1
    assert character.inventory[0].name == "短剑"
    assert character.inventory[0].unit == "把"
    assert character.inventory[0].quantity == 2
    assert character.inventory[0].display() == "短剑（2把）"


def test_normalize_merges_duplicate_name_stacks():
    items = normalize_inventory_list(
        [
            InventoryItem(name="短剑", quantity=1, unit="把"),
            InventoryItem(name="短剑", quantity=1, unit="个"),
        ]
    )
    assert len(items) == 1
    assert items[0].quantity == 2
    assert items[0].unit == "把"


def test_matches_does_not_match_substring_name():
    gold = InventoryItem(name="定金币", quantity=15, unit="枚")
    coin = InventoryItem(name="金币", quantity=3, unit="枚")
    assert gold.matches("定金币")
    assert not gold.matches("金币")
    assert coin.matches("金币")
    assert not coin.matches("定金币")
