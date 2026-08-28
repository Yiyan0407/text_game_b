from game.models import Character, GameState, Quest
from game.narrative_time import (
    advance_narrative_clock,
    apply_story_clock_label,
    apply_time_patch,
    estimate_turn_minutes,
    format_clock,
    format_duration,
    infer_opening_time_label,
    initialize_story_clock_from_scenario,
    parse_explicit_wait_minutes,
    parse_time_label,
)
from game.results import ActionRouteResult, DeadlinePatch, TimePatch
from game.scenario import Scenario
from game.state_patch import patch_from_dict


def test_parse_time_label():
    assert parse_time_label("第1天 23:50") == (1, 23, 50)
    assert parse_time_label("周五深夜") is None


def test_format_clock_uses_story_anchor():
    assert format_clock(0, 23 * 60) == "第1天 23:00"
    assert format_clock(90, 23 * 60) == "第2天 00:30"


def test_infer_opening_time_label_for_night_scene():
    scenario = Scenario(
        id="night_case",
        title="夜班",
        opening_prompt="深夜的报社编辑部，匿名账号发来压缩包。",
        opening_scene_name="报社·夜班工位",
    )
    assert infer_opening_time_label(scenario) == "第1天 23:00"


def test_initialize_story_clock_from_scenario():
    scenario = Scenario(
        id="night_case",
        title="夜班",
        opening_prompt="深夜的报社编辑部。",
    )
    state = GameState()
    initialize_story_clock_from_scenario(state, scenario)
    assert state.story_start_absolute_minutes == 23 * 60 + 30
    assert state.elapsed_minutes == 0
    assert state.narrative_time_label == "第1天 23:30"


def test_apply_story_clock_label_reanchors_opening():
    state = GameState()
    apply_story_clock_label(state, "第1天 22:15")
    assert state.story_start_absolute_minutes == 22 * 60 + 15
    assert state.narrative_time_label == "第1天 22:15"


def test_advance_narrative_clock_keeps_night_progression():
    state = GameState(story_start_absolute_minutes=23 * 60, elapsed_minutes=0)
    advance_narrative_clock(state, 45)
    assert state.narrative_time_label == "第1天 23:45"


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


def test_deadline_penalties_fail_quest_and_damage():
    state = GameState(
        elapsed_minutes=0,
        active_quests=[Quest(id="rescue", title="解救人质", status="active")],
        deadlines=[
            {
                "id": "rescue",
                "label": "解救人质",
                "due_at_minutes": 10,
                "status": "pending",
                "consequence": "爆炸导致受伤",
                "created_at_minutes": 0,
                "fail_quest_ids": ["rescue"],
                "hp_loss": 7,
            }
        ],
    )
    character = Character(name="测试", hp=20, max_hp=20)
    events = advance_narrative_clock(state, 15, character)
    assert state.active_quests[0].status == "failed"
    assert character.hp == 13
    assert any("任务失败" in event for event in events)
    assert any("伤害" in event for event in events)


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
                        "fail_quest_ids": ["q1"],
                        "hp_loss": 5,
                    }
                ]
            }
        }
    )
    assert patch.time is not None
    assert patch.time.deadlines[0].label == "炸弹爆炸"
    assert patch.time.deadlines[0].due_in_minutes == 30
    assert patch.time.deadlines[0].fail_quest_ids == ["q1"]
    assert patch.time.deadlines[0].hp_loss == 5


def test_format_duration():
    assert format_duration(90) == "1 小时 30 分"
    assert format_duration(1440) == "1 天"
