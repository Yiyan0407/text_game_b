import pytest

from game.models import Character, GameState
from game.results import ActionRouteResult
from game.scenario import Scenario
from game.turn_context import TurnContext
from game.settlement_plan import (
    OPENING_SETTLEMENT_PLAN,
    SettlementPlan,
    SettlementRouterError,
    parse_settlement_plan,
)
from game.turn_router import (
    format_settlement_plan_event,
    needs_post_kp_mechanical,
    resolve_settlement_plan,
)


def _ctx(**kwargs) -> TurnContext:
    defaults = {
        "user_input": "观察",
        "character": Character(name="测试"),
        "game_state": GameState(),
        "scenario": Scenario(id="t", title="测试"),
        "history": [],
        "kp_response": "你观察四周。",
    }
    defaults.update(kwargs)
    return TurnContext(**defaults)


def test_needs_post_kp_mechanical_purchase():
    route = ActionRouteResult(approved=True, item_usage="purchase")
    assert needs_post_kp_mechanical(route, GameState()) is True


def test_needs_post_kp_mechanical_use():
    route = ActionRouteResult(approved=True, item_usage="use")
    assert needs_post_kp_mechanical(route, GameState()) is True


def test_needs_post_kp_mechanical_observe_false():
    route = ActionRouteResult(approved=True, item_usage="none")
    assert needs_post_kp_mechanical(route, GameState()) is False


def test_parse_settlement_plan():
    plan = parse_settlement_plan(
        {
            "tasks": {
                "inventory_sync": True,
                "skill_sync": False,
                "time_sync": True,
                "world_sync": True,
            },
            "reason": "拾取并移动",
        }
    )
    assert plan == SettlementPlan(True, False, True, True, "拾取并移动")


def test_parse_settlement_plan_invalid():
    with pytest.raises(SettlementRouterError):
        parse_settlement_plan({"tasks": "bad"})


def test_resolve_opening_plan():
    ctx = _ctx(is_opening=True)
    plan = resolve_settlement_plan(ctx)
    assert plan == OPENING_SETTLEMENT_PLAN


def test_resolve_rejected_plan():
    ctx = _ctx(rejected=True)
    plan = resolve_settlement_plan(ctx)
    assert plan.inventory_sync is False
    assert plan.time_sync is False


def test_resolve_missing_router_raises():
    ctx = _ctx()
    with pytest.raises(SettlementRouterError, match="缺少 Settlement Router plan"):
        resolve_settlement_plan(ctx)


def test_format_settlement_plan_event():
    text = format_settlement_plan_event(
        SettlementPlan(True, False, True, False, "纯对话")
    )
    assert "结算路由" in text
    assert "inventory" in text
    assert "time" in text
