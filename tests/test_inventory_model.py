from chain.action_router import ActionRouter
from game.inventory import InventoryItem, normalize_inventory_list
from game.models import Character, GameState
from game.orchestrator import GameOrchestrator
from game.results import ActionRouteResult


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


def test_format_detail_includes_description():
    item = InventoryItem(
        name="破禁符",
        quantity=1,
        unit="张",
        description="可短暂破开低阶禁制。",
    )
    assert item.format_detail() == "破禁符（1张） — 可短暂破开低阶禁制。"


def test_merge_preserves_description():
    character = Character(name="测试")
    character.add_inventory_item("短剑", description="精钢打造，锋利耐用。")
    character.add_inventory_item("短剑", quantity=1, unit="把")
    assert character.inventory[0].description == "精钢打造，锋利耐用。"


def test_parse_vague_quantity_renwu():
    item = InventoryItem.parse("止血凝胶（若干）")
    assert item.name == "止血凝胶"
    assert item.quantity == 3
    assert item.unit == "个"


def test_parse_ji_ping_quantity():
    item = InventoryItem.parse("止血凝胶（几瓶）")
    assert item.quantity == 3
    assert item.unit == "瓶"


def test_parse_bank_card_with_wan_credits():
    item = InventoryItem.parse("银行卡（19万信用点）")
    assert item.name == "银行卡"
    assert item.quantity == 190_000
    assert item.unit == "信用点"


def test_normalize_repairs_malformed_wan_unit():
    items = normalize_inventory_list(
        [InventoryItem(name="银行卡", quantity=1, unit="19万信用点")]
    )
    assert len(items) == 1
    assert items[0].quantity == 190_000
    assert items[0].unit == "信用点"


def test_purchase_with_credit_card_balance():
    character = Character(name="测试", inventory=["银行卡（19万信用点）"])
    route = ActionRouteResult(
        approved=True,
        item_usage="purchase",
        payment_items=["银行卡"],
        payment_quantity=2500,
        referenced_items=["信号干扰器", "EMP脉冲器"],
    )
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is True

    events = GameOrchestrator._execute_purchase(route, character)
    assert not any("支付失败" in event for event in events)
    assert character.inventory[0].quantity == 187_500


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
