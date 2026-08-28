from game.models import GameState
from game.narrative_time import (
    advance_narrative_clock,
    apply_time_patch,
    estimate_turn_minutes,
    format_duration,
    parse_explicit_wait_minutes,
)
from game.results import ActionRouteResult, DeadlinePatch, TimePatch
from game.state_patch import patch_from_dict


def test_parse_explicit_wait_minutes():
    assert parse_explicit_wait_minutes("我在这里等三天", elapsed_minutes=0) == 3 * 24 * 60
    assert parse_explicit_wait_minutes("等待6小时", elapsed_minutes=120) == 360
    assert parse_explicit_wait_minutes("观察周围", elapsed_minutes=0) is None


def test_advance_narrative_clock_triggers_deadline():
    state = GameState(
        elapsed_minutes=0,
        deadlines=[
            {
                "id": "bomb",
                "label": "炸弹爆炸",
                "due_at_minutes": 30,
                "status": "pending",
                "consequence": "爆炸发生",
                "created_at_minutes": 0,
            }
        ],
    )
    events = advance_narrative_clock(state, 35)
    assert state.elapsed_minutes == 35
    assert any("时限已到" in event for event in events)
    assert state.deadlines[0].status == "triggered"
    assert any("炸弹爆炸" in fact for fact in state.memory_facts)


def test_apply_time_patch_adds_deadline():
    state = GameState(elapsed_minutes=10)
    events = apply_time_patch(
        state,
        TimePatch(
            deadlines=[
                DeadlinePatch(
                    id="mission",
                    label="行动开始",
                    due_in_minutes=360,
                    consequence="接头人现身",
                )
            ]
        ),
    )
    assert state.deadlines[0].due_at_minutes == 370
    assert any("已登记时限" in event for event in events)


def test_estimate_turn_minutes_for_wait():
    route = ActionRouteResult(approved=True, action_intent="等待")
    minutes = estimate_turn_minutes(route, "我决定等三天再行动", GameState())
    assert minutes == 3 * 24 * 60


def test_patch_from_dict_parses_time():
    patch = patch_from_dict(
        {
            "time": {
                "deadlines": [
                    {
                        "label": "炸弹爆炸",
                        "due_in_minutes": 30,
                        "consequence": "爆炸",
                    }
                ]
            }
        }
    )
    assert patch.time is not None
    assert patch.time.deadlines[0].label == "炸弹爆炸"
    assert patch.time.deadlines[0].due_in_minutes == 30


def test_format_duration():
    assert format_duration(90) == "1 小时 30 分"
    assert format_duration(1440) == "1 天"
