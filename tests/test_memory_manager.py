from unittest.mock import MagicMock

from chain.memory_manager import LongTermMemoryManager
from chain.summarizer import _parse_fact_lines
from game.models import ChatMessage, GameState


def test_parse_fact_lines():
    text = "- 获得了加密芯片\n* 老K 是线人\n1. 承诺明天交货"
    facts = _parse_fact_lines(text)
    assert len(facts) == 3
    assert "获得了加密芯片" in facts[0]


def test_add_memory_facts_dedupe():
    state = GameState()
    state.add_memory_facts(["获得了芯片", "获得了芯片"], max_facts=10)
    assert len(state.memory_facts) == 1


def test_memory_manager_periodic_summary():
    summarizer = MagicMock()
    summarizer.merge_summary.return_value = "合并摘要"
    summarizer.extract_facts.return_value = ["新事实"]
    manager = LongTermMemoryManager(summarizer)
    manager.summary_interval = 6

    state = GameState(turn_count=6, last_summarized_turn=0)
    history = [ChatMessage(role="user", content="test")]

    manager.process_after_turn(state, history)
    summarizer.merge_summary.assert_called_once()
    summarizer.extract_facts.assert_called_once()
    assert state.story_summary == "合并摘要"
    assert "新事实" in state.memory_facts
    assert state.last_summarized_turn == 6


def test_format_for_prompt_includes_facts():
    state = GameState(
        turn_count=50,
        memory_facts=["玩家欠老K一个人情"],
        story_summary="进行中",
    )
    text = state.format_for_prompt()
    assert "关键事实" in text
    assert "老K" in text
