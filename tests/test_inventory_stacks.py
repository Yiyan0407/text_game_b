from chain.action_router import ActionRouter
from game.models import Character, GameState
from game.orchestrator import GameOrchestrator
from game.results import ActionRouteResult


def test_consume_inventory_quantity_from_stack():
    character = Character(
        name="测试",
        inventory=["定金币（15枚）", "食盐（一袋）"],
    )
    ok, message = character.consume_inventory_quantity("定金币", 1)
    assert ok is True
    assert "14枚" in message
    assert character.has_inventory_item("定金币（14枚）")
    assert character.has_inventory_item("食盐（一袋）")


def test_execute_purchase_deducts_payment_and_adds_goods():
    character = Character(name="测试", inventory=["定金币（15枚）"])
    route = ActionRouteResult(
        approved=True,
        item_usage="purchase",
        payment_items=["定金币"],
        payment_quantity=1,
        referenced_items=["食盐（一袋）"],
    )
    events = GameOrchestrator._execute_purchase(route, character)
    assert any("14枚" in event for event in events)
    assert any("食盐（一袋）" in event for event in events)
    assert character.has_inventory_item("定金币（14枚）")
    assert character.has_inventory_item("食盐（一袋）")


def test_execute_purchase_fails_without_payment_items():
    character = Character(name="测试", inventory=["定金币（15枚）"])
    route = ActionRouteResult(
        approved=True,
        item_usage="purchase",
        payment_items=[],
        referenced_items=["食盐（一袋）"],
    )
    events = GameOrchestrator._execute_purchase(route, character)
    assert events == ["支付失败：未指定支付物品。"]
    assert character.has_inventory_item("定金币（15枚）")
    assert not character.has_inventory_item("食盐（一袋）")


def test_execute_purchase_fails_when_insufficient_funds():
    character = Character(name="测试", inventory=["定金币（1枚）"])
    route = ActionRouteResult(
        approved=True,
        item_usage="purchase",
        payment_items=["定金币"],
        payment_quantity=5,
        referenced_items=["食盐（一袋）"],
    )
    events = GameOrchestrator._execute_purchase(route, character)
    assert any("支付失败" in event for event in events)
    assert character.has_inventory_item("定金币（1枚）")
    assert not character.has_inventory_item("食盐（一袋）")


def test_validate_purchase_requires_payment_items():
    route = ActionRouteResult(
        approved=True,
        item_usage="purchase",
        payment_items=[],
        referenced_items=["食盐（一袋）"],
    )
    character = Character(name="测试", inventory=["定金币（15枚）"])
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is False
    assert "payment_items" in result.rejection_reason


def test_validate_purchase_requires_sufficient_quantity():
    route = ActionRouteResult(
        approved=True,
        item_usage="purchase",
        payment_items=["定金币"],
        payment_quantity=5,
        referenced_items=["食盐（一袋）"],
    )
    character = Character(name="测试", inventory=["定金币（3枚）"])
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is False
    assert "数量不足" in result.rejection_reason


def test_validate_purchase_requires_payment_in_inventory():
    route = ActionRouteResult(
        approved=True,
        item_usage="purchase",
        payment_items=["定金币"],
        referenced_items=["食盐（一袋）"],
    )
    character = Character(name="测试", inventory=["铜板（3枚）"])
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is False
    assert "定金币" in result.rejection_reason
