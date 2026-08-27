from unittest.mock import MagicMock

from chain.memory_manager import LongTermMemoryManager
from game.models import ChatMessage, GameState
from game.orchestrator import GameOrchestrator


def test_default_opening_suggestions_use_quest_and_scene():
    from game.orchestrator import GameOrchestrator
    from game.models import Quest
    from game.scenario import Scenario

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
