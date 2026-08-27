from unittest.mock import MagicMock

from chain.memory_manager import LongTermMemoryManager
from game.models import Character, ChatMessage, GameState
from game.narrative_brief import build_narrative_brief_static, merge_narrative_brief_with_state
from game.orchestrator import GameOrchestrator
from game.results import ActionRouteResult
from game.scenario import Scenario


def test_default_opening_suggestions_use_quest_and_scene():
    from game.models import Quest

    scenario = Scenario(id="test", title="测试", opening_scene_name="酒馆")
    state = GameState(
        current_scene="灰港·海鸥尾酒馆",
        active_quests=[Quest(id="q1", title="调查失踪渔民", description="")],
    )
    suggestions = GameOrchestrator._default_opening_suggestions(scenario, state)
    assert len(suggestions) == 3
    assert any("失踪渔民" in item for item in suggestions)


def test_memory_process_after_turn_interval():
    summarizer = MagicMock()
    summarizer.merge_summary.return_value = "新的摘要"
    summarizer.extract_facts.return_value = []
    memory = LongTermMemoryManager(summarizer)
    memory.summary_interval = 6

    orchestrator = GameOrchestrator.__new__(GameOrchestrator)
    orchestrator.memory = memory

    game_state = GameState(turn_count=5, last_summarized_turn=0)
    history = [ChatMessage(role="user", content="test")]

    memory.process_after_turn(game_state, history)
    summarizer.merge_summary.assert_not_called()

    game_state.turn_count = 6
    memory.process_after_turn(game_state, history)
    summarizer.merge_summary.assert_called_once()
    assert game_state.story_summary == "新的摘要"
    assert game_state.last_summarized_turn == 6


def test_narrative_brief_static_contains_route_fields():
    route = ActionRouteResult(
        approved=True,
        action_intent="观察周围",
        scope_stop="观察完毕",
        must_not_narrate=["离开场景"],
    )
    brief = build_narrative_brief_static("观察周围", route, ["敏捷检定 成功"])
    assert "【叙事简报】" in brief
    assert "观察周围" in brief
    assert "敏捷检定" in brief


def test_merge_narrative_brief_includes_state():
    character = Character(name="测试")
    game_state = GameState(current_scene="酒馆")
    brief = merge_narrative_brief_with_state(
        "静态段",
        character,
        game_state,
        state_events=["已记录 NPC：酒保（neutral）"],
    )
    assert "【当前状态】" in brief
    assert "酒馆" in brief
    assert "酒保" in brief
