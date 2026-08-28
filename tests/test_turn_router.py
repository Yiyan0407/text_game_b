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
    }
    defaults.update(kwargs)
    return TurnContext(**defaults)


def test_item_sync_skipped_when_rejected():
    ctx = _ctx(rejected=True, kp_response="你获得了短剑。")
    assert should_run_item_sync(ctx) is False


def test_item_sync_runs_on_mechanical_gain():
    ctx = _ctx(
        kp_response="铁匠把连弩递给你。",
        mechanical_events=["获得：连弩"],
        route=ActionRouteResult(approved=True),
    )
    assert should_run_item_sync(ctx) is True


def test_item_sync_runs_on_kp_implant_narrative():
    ctx = _ctx(
        user_input="检查义体",
        kp_response="体内有反应增强层与视觉辅助芯片。",
    )
    assert should_run_item_sync(ctx) is True


def test_item_sync_skipped_on_pure_dialogue():
    ctx = _ctx(
        user_input="这里天气怎么样？",
        kp_response="雨还在下，海风很冷。",
    )
    assert should_run_item_sync(ctx) is False
