from game.deadline_grounding import (
    build_deadline_corpus,
    filter_deadline_patches,
    is_deadline_grounded,
)
from game.models import GameState
from game.results import DeadlinePatch, TimePatch
from game.narrative_time import apply_turn_time_from_patch


def test_is_deadline_grounded_by_full_label_or_fragment():
    assert is_deadline_grounded("传送门自动启动", "传送门启动时间约在08:15")
    assert is_deadline_grounded("炸弹爆炸", "地下室发现定时炸弹，约30分钟后爆炸")
    assert not is_deadline_grounded("炸弹爆炸", "里昂已成功穿越至2020年纽约千川科技大楼地下室")


def test_filter_deadline_patches_blocks_template_without_context():
    deadlines = [
        DeadlinePatch(label="炸弹爆炸", due_in_minutes=30),
        DeadlinePatch(label="传送门自动启动", due_in_minutes=13),
    ]
    corpus = build_deadline_corpus(
        user_input="看地图，规划行动",
        memory_facts=["传送门启动时间约在08:15"],
    )
    kept, events = filter_deadline_patches(deadlines, corpus)
    assert [item.label for item in kept] == ["传送门自动启动"]
    assert any("炸弹爆炸" in event for event in events)


def test_apply_turn_time_blocks_ungrounded_bomb_on_scene_change():
    state = GameState()
    state.add_memory_facts(
        ["里昂已成功穿越至2020年纽约千川科技大楼地下室"],
        max_facts=50,
    )
    events = apply_turn_time_from_patch(
        state,
        TimePatch(
            advance_minutes=3,
            advance_reason="落地后适应环境",
            deadlines=[DeadlinePatch(label="炸弹爆炸", due_in_minutes=30)],
        ),
        route=None,
        user_input="小爱，更新黑客模块，先看地图规划行动",
        character=None,
        has_time_field=True,
        recent_history="你踏入传送门，光芒消退，你到了地下室。",
    )
    assert not state.deadlines
    assert any("跳过无依据时限" in event for event in events)
    assert not any("已登记时限：炸弹爆炸" in event for event in events)


def test_apply_turn_time_allows_grounded_deadline():
    state = GameState()
    events = apply_turn_time_from_patch(
        state,
        TimePatch(
            deadlines=[DeadlinePatch(label="传送门自动启动", due_in_minutes=13)],
        ),
        route=None,
        user_input="准备穿越",
        character=None,
        has_time_field=True,
        recent_history="易玖说传送门启动时间约在08:15。",
    )
    assert len(state.deadlines) == 1
    assert state.deadlines[0].label == "传送门自动启动"
    assert any("已登记时限" in event for event in events)
