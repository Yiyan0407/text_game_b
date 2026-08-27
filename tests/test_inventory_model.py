from game.inventory import InventoryItem, normalize_inventory_list


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


def test_matches_fuzzy_name():
    item = InventoryItem(name="定金币", quantity=15, unit="枚")
    assert item.matches("定金币")
    assert item.matches("定金币（15枚）")
