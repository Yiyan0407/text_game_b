from unittest.mock import MagicMock

from chain.memory_manager import LongTermMemoryManager
from game.models import ChatMessage, GameState
from game.orchestrator import GameOrchestrator


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
