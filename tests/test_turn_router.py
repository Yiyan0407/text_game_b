from game.models import Character, GameState
from game.results import ActionRouteResult
from game.scenario import Scenario
from game.turn_context import TurnContext
from game.turn_router import should_run_item_sync


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


def test_item_sync_skipped_when_rejected():
    ctx = _ctx(rejected=True, kp_response="你获得了短剑。")
    assert should_run_item_sync(ctx) is False


def test_item_sync_skipped_when_no_kp_response():
    ctx = _ctx(kp_response="")
    assert should_run_item_sync(ctx) is False


def test_item_sync_runs_by_default():
    ctx = _ctx(
        user_input="一口吃完三明治，把外包的工资放进口袋",
        kp_response="你在前台领了薄薄一沓现金。",
    )
    assert should_run_item_sync(ctx) is True


def test_item_sync_runs_on_mechanical_gain():
    ctx = _ctx(
        kp_response="铁匠把连弩递给你。",
        mechanical_events=["获得：连弩"],
        route=ActionRouteResult(approved=True),
    )
    assert should_run_item_sync(ctx) is True


def test_item_sync_skipped_when_router_sets_false():
    ctx = _ctx(
        user_input="这里天气怎么样？",
        kp_response="雨还在下，海风很冷。",
        route=ActionRouteResult(approved=True, sync_inventory=False),
    )
    assert should_run_item_sync(ctx) is False


def test_item_sync_runs_on_pickup_route():
    ctx = _ctx(
        user_input="捡起地上的钥匙",
        kp_response="你捡起了钥匙。",
        route=ActionRouteResult(
            approved=True,
            item_usage="pickup",
            referenced_items=["钥匙"],
        ),
    )
    assert should_run_item_sync(ctx) is True


def test_route_parses_sync_inventory():
    from chain.action_router import _route_from_dict

    assert _route_from_dict({"approved": True, "sync_inventory": False}).sync_inventory is False
    assert _route_from_dict({"approved": True}).sync_inventory is True
