from game.models import Character, GameState, Quest
from game.narrative_time import (
    advance_narrative_clock,
    apply_story_clock_label,
    apply_time_patch,
    apply_turn_time_from_patch,
    format_clock,
    format_duration,
    initialize_story_clock_from_scenario,
    parse_explicit_wait_minutes,
    parse_stated_action_minutes,
    parse_time_label,
    resolve_turn_advance_minutes,
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


def test_initialize_story_clock_from_scenario_is_noop():
    scenario = Scenario(
        id="night_case",
        title="夜班",
        opening_prompt="深夜的报社编辑部。",
    )
    state = GameState()
    initialize_story_clock_from_scenario(state, scenario)
    assert state.story_start_absolute_minutes == 8 * 60
    assert state.elapsed_minutes == 0
    assert state.narrative_time_label == ""


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


def test_parse_stated_action_minutes():
    from game.narrative_time import parse_stated_action_minutes

    assert parse_stated_action_minutes("我需要15分钟完成全部义体植入") == 15
    assert parse_stated_action_minutes("机器人会在15分钟内帮我完成") == 15


def test_apply_time_patch_ignores_conflicting_time_label():
    state = GameState(story_start_absolute_minutes=8 * 60, elapsed_minutes=20)
    apply_time_patch(
        state,
        TimePatch(advance_minutes=15, time_label="第1天 08:50"),
    )
    assert state.elapsed_minutes == 35
    assert state.narrative_time_label == "第1天 08:35"


def test_add_deadline_skips_duplicate_label():
    from game.narrative_time import add_deadline

    state = GameState(elapsed_minutes=10)
    first = add_deadline(
        state,
        DeadlinePatch(label="传送倒计时", due_in_minutes=30),
    )
    second = add_deadline(
        state,
        DeadlinePatch(label="传送倒计时", due_in_minutes=24),
    )
    assert first
    assert second == []
    assert len(state.deadlines) == 1
    assert state.deadlines[0].due_at_minutes == 40


def test_resolve_turn_advance_minutes_prefers_agent_over_stated():
    route = ActionRouteResult(approved=True, action_intent="义体植入")
    minutes = resolve_turn_advance_minutes(
        TimePatch(advance_minutes=30),
        route=route,
        user_input="我需要15分钟完成全部义体植入",
        game_state=GameState(elapsed_minutes=20),
        has_time_field=True,
    )
    assert minutes == 30


def test_format_player_stated_duration_hint():
    from game.narrative_time import format_player_stated_duration_hint

    hint = format_player_stated_duration_hint("我需要15分钟完成")
    assert "15" in hint
    assert "合理" in hint
    assert format_player_stated_duration_hint("观察周围") == "（无）"


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
    assert state.deadlines[0].status == "due"
    assert not any("任务失败" in event for event in events)
    assert any("炸弹爆炸" in fact for fact in state.memory_facts)


def test_deadline_penalties_only_on_enforce():
    from game.narrative_time import enforce_deadline

    state = GameState(
        elapsed_minutes=15,
        active_quests=[Quest(id="rescue", title="解救人质", status="active")],
        deadlines=[
            {
                "id": "rescue",
                "label": "解救人质",
                "due_at_minutes": 10,
                "status": "due",
                "consequence": "爆炸导致受伤",
                "created_at_minutes": 0,
                "fail_quest_ids": ["rescue"],
                "hp_loss": 7,
            }
        ],
    )
    character = Character(name="测试", hp=20, max_hp=20)
    events = enforce_deadline(state, "rescue", character)
    assert state.active_quests[0].status == "failed"
    assert character.hp == 13
    assert state.deadlines[0].status == "resolved"
    assert any("任务失败" in event for event in events)
    assert any("伤害" in event for event in events)


def test_advance_narrative_clock_does_not_auto_fail_quest():
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
    assert state.active_quests[0].status == "active"
    assert character.hp == 20
    assert state.deadlines[0].status == "due"
    assert not any("任务失败" in event for event in events)


def test_cancel_deadline_works_for_due_status():
    state = GameState(
        elapsed_minutes=20,
        deadlines=[
            {
                "id": "log_check",
                "label": "安保检查日志",
                "due_at_minutes": 10,
                "status": "due",
                "consequence": "暴露入侵",
                "created_at_minutes": 0,
            }
        ],
    )
    from game.narrative_time import cancel_deadline

    message = cancel_deadline(state, "log_check")
    assert message is not None
    assert "化解" in message
    assert state.deadlines[0].status == "cancelled"


def test_cancel_deadline_matches_label():
    state = GameState(
        elapsed_minutes=20,
        deadlines=[
            {
                "id": "abc123",
                "label": "安保人员检查B2-07异常日志",
                "due_at_minutes": 10,
                "status": "due",
                "consequence": "暴露",
                "created_at_minutes": 0,
            }
        ],
    )
    from game.narrative_time import cancel_deadline

    message = cancel_deadline(state, "安保人员检查B2-07异常日志")
    assert message is not None
    assert state.deadlines[0].status == "cancelled"


def test_apply_time_patch_warns_when_cancel_not_found():
    state = GameState()
    events = apply_time_patch(state, TimePatch(cancel_deadline_ids=["missing"]))
    assert any("未找到" in event for event in events)


def test_apply_turn_time_zero_minutes_marks_overdue_pending_due():
    state = GameState(
        elapsed_minutes=20,
        deadlines=[
            {
                "id": "bomb",
                "label": "炸弹爆炸",
                "due_at_minutes": 10,
                "status": "pending",
                "consequence": "爆炸",
                "created_at_minutes": 0,
            }
        ],
    )
    events = apply_turn_time_from_patch(
        state,
        TimePatch(),
        route=None,
        user_input="继续观察",
        character=None,
        has_time_field=True,
    )
    assert state.deadlines[0].status == "due"
    assert any("时限已到" in event for event in events)


def test_enforce_deadline_triggers_overdue_pending():
    state = GameState(
        elapsed_minutes=20,
        active_quests=[Quest(id="q1", title="任务", status="active")],
        deadlines=[
            {
                "id": "bomb",
                "label": "炸弹爆炸",
                "due_at_minutes": 10,
                "status": "pending",
                "consequence": "爆炸",
                "created_at_minutes": 0,
                "fail_quest_ids": ["q1"],
            }
        ],
    )
    events = apply_time_patch(state, TimePatch(enforce_deadline_ids=["bomb"]))
    assert state.deadlines[0].status == "resolved"
    assert state.active_quests[0].status == "failed"
    assert any("后果成立" in event for event in events)


def test_coerce_quest_list_allows_missing_title():
    from game.state_patch import _coerce_quest_list

    quests = _coerce_quest_list([{"quest_id": "q1", "status": "completed"}])
    assert len(quests) == 1
    assert quests[0].quest_id == "q1"
    assert quests[0].title == ""
    state = GameState(
        elapsed_minutes=20,
        active_quests=[Quest(id="q1", title="任务", status="active")],
        deadlines=[
            {
                "id": "bomb",
                "label": "炸弹爆炸",
                "due_at_minutes": 10,
                "status": "due",
                "consequence": "爆炸",
                "created_at_minutes": 0,
                "fail_quest_ids": ["q1"],
            }
        ],
    )
    events = apply_time_patch(state, TimePatch(enforce_deadline_ids=["bomb"]))
    assert state.active_quests[0].status == "failed"
    assert any("后果成立" in event for event in events)


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


def test_resolve_turn_advance_minutes_explicit_wait():
    route = ActionRouteResult(approved=True, action_intent="等待")
    minutes = resolve_turn_advance_minutes(
        None,
        route=route,
        user_input="我决定等三天再行动",
        game_state=GameState(),
        has_time_field=False,
    )
    assert minutes == 3 * 24 * 60


def test_resolve_turn_advance_minutes_no_patch_without_agent():
    route = ActionRouteResult(approved=True, action_intent="继续")
    minutes = resolve_turn_advance_minutes(
        None,
        route=route,
        user_input="好的",
        game_state=GameState(),
        has_time_field=False,
    )
    assert minutes == 0


def test_format_turn_time_hint():
    from game.narrative_time import format_turn_time_hint

    hint = format_turn_time_hint(["⏳ 时间推进 2 分（第1天 08:02）"])
    assert "2 分" in hint
    assert "状态同步器" in hint


def test_resolve_turn_advance_minutes_prefers_agent():
    from game.results import TimePatch

    route = ActionRouteResult(approved=True, action_intent="质问")
    agent_minutes = resolve_turn_advance_minutes(
        TimePatch(advance_minutes=2),
        route=route,
        user_input="你是谁？",
        game_state=GameState(),
        has_time_field=True,
    )
    assert agent_minutes == 2


def test_resolve_turn_advance_minutes_without_time_field_stays_zero():
    route = ActionRouteResult(approved=True, action_intent="继续")
    minutes = resolve_turn_advance_minutes(
        None,
        route=route,
        user_input="好的",
        game_state=GameState(),
        has_time_field=False,
    )
    assert minutes == 0


def test_apply_turn_time_from_patch_uses_agent_value():
    from game.results import TimePatch

    state = GameState()
    events = apply_turn_time_from_patch(
        state,
        TimePatch(advance_minutes=2, advance_reason="与门卫简短交谈"),
        route=ActionRouteResult(approved=True, action_intent="询问"),
        user_input="你是谁？",
        character=None,
        has_time_field=True,
    )
    assert state.elapsed_minutes == 2
    assert any("时间推进" in event for event in events)
    assert any("与门卫简短交谈" in event for event in events)


def test_apply_turn_time_from_patch_without_agent_does_not_advance():
    state = GameState()
    events = apply_turn_time_from_patch(
        state,
        None,
        route=ActionRouteResult(approved=True, action_intent="移动"),
        user_input="接受邀请前往B2层",
        character=None,
        has_time_field=False,
    )
    assert state.elapsed_minutes == 0
    assert not any("时间推进" in event for event in events)


def test_apply_state_patch_skips_time_when_disabled():
    from game.results import StatePatch
    from game.state_patch import apply_state_patch

    state = GameState()
    character = Character(name="测试")
    events = apply_state_patch(
        StatePatch(time=TimePatch(advance_minutes=10, advance_reason="不应生效")),
        character,
        state,
        user_input="前往远处",
        apply_time=False,
    )
    assert state.elapsed_minutes == 0
    assert not any("时间推进" in event for event in events)


def test_patch_from_dict_parses_advance_reason():
    patch = patch_from_dict(
        {
            "time": {
                "advance_minutes": 5,
                "advance_reason": "搜查设备间端口",
            }
        }
    )
    assert patch.time is not None
    assert patch.time.advance_minutes == 5
    assert patch.time.advance_reason == "搜查设备间端口"


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
