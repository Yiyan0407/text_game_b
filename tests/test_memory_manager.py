from unittest.mock import MagicMock

from chain.memory_manager import LongTermMemoryManager
from chain.summarizer import _parse_fact_lines
from game.memory_journal import entry_from_text, journal_total_chars, trim_memory_journal
from game.models import ChatMessage, GameState


def test_parse_fact_lines():
    text = "- 获得了加密芯片\n* 老K 是线人\n1. 承诺明天交货"
    facts = _parse_fact_lines(text)
    assert len(facts) == 3
    assert "获得了加密芯片" in facts[0]


def test_add_memory_facts_dedupe():
    state = GameState()
    state.add_memory_facts(["获得了加密芯片", "获得了加密芯片"], max_facts=10)
    assert len(state.memory_facts) == 1


def test_memory_manager_periodic_summary():
    summarizer = MagicMock()
    summarizer.merge_summary.return_value = "合并摘要"
    summarizer.extract_facts.return_value = ["老K答应帮忙潜入实验室"]
    manager = LongTermMemoryManager(summarizer)
    manager.summary_interval = 6

    state = GameState(turn_count=6, last_summarized_turn=0)
    history = [ChatMessage(role="user", content="test")]

    manager.process_after_turn(state, history)
    summarizer.merge_summary.assert_called_once()
    summarizer.extract_facts.assert_called_once()
    assert state.story_summary == "合并摘要"
    assert any("老K" in fact for fact in state.memory_facts)
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


def test_should_compress_journal_at_count_threshold():
    summarizer = MagicMock()
    manager = LongTermMemoryManager(summarizer)
    manager.memory_journal_compress_at = 5
    manager.memory_journal_max_chars = 99999

    state = GameState(turn_count=1)
    state.memory_journal = [entry_from_text(f"事实{i}") for i in range(4)]
    assert manager._should_compress_journal(state) is False

    state.memory_journal.append(entry_from_text("第五条"))
    assert manager._should_compress_journal(state) is True


def test_should_compress_journal_at_char_threshold():
    summarizer = MagicMock()
    manager = LongTermMemoryManager(summarizer)
    manager.memory_journal_compress_at = 99
    manager.memory_journal_max_chars = 50

    state = GameState(turn_count=1)
    state.memory_journal = [entry_from_text("a" * 30), entry_from_text("b" * 25)]
    assert manager._should_compress_journal(state) is True


def test_compress_journal_keeps_pinned_and_reduces_unpinned():
    summarizer = MagicMock()
    pinned = entry_from_text("置顶线索", topic="线索")
    pinned = pinned.model_copy(update={"pinned": True})
    unpinned = [entry_from_text(f"未置顶{i}", topic="综合") for i in range(8)]
    compressed = [
        entry_from_text("合并后的综合记忆1", topic="综合"),
        entry_from_text("合并后的综合记忆2", topic="综合"),
    ]
    summarizer.compress_memory_entries.return_value = compressed

    manager = LongTermMemoryManager(summarizer)
    manager.memory_journal_compress_at = 5
    manager.max_memory_facts = 50

    state = GameState(turn_count=10)
    state.memory_journal = [pinned, *unpinned]

    manager._compress_journal(state)

    summarizer.compress_memory_entries.assert_called_once()
    assert state.memory_journal[0].pinned is True
    assert state.memory_journal[0].text == "置顶线索"
    assert len(state.memory_journal) == 3
    assert all(not entry.pinned for entry in state.memory_journal[1:])
    assert len(state.memory_journal_archive) == 8
    player_entries = state.player_memory_entries()
    assert len(player_entries) == 11
    assert any(entry.text == "置顶线索" for entry in player_entries)


def test_compress_journal_falls_back_to_trim_when_llm_empty():
    summarizer = MagicMock()
    summarizer.compress_memory_entries.return_value = []

    manager = LongTermMemoryManager(summarizer)
    manager.memory_journal_compress_at = 3
    manager.max_memory_facts = 2

    state = GameState(turn_count=1)
    state.memory_journal = [entry_from_text(f"事实{i}") for i in range(4)]

    manager._compress_journal(state)

    assert len(state.memory_journal) == 2
    assert state.memory_journal[-1].text == "事实3"
    assert len(state.memory_journal_archive) == 2
    archived_texts = {entry.text for entry in state.memory_journal_archive}
    assert archived_texts == {"事实0", "事实1"}


def test_add_memory_entries_archives_trimmed_facts():
    state = GameState()
    state.add_memory_facts([f"关键事实条目{i}" for i in range(5)], max_facts=3)
    assert len(state.memory_journal) == 3
    assert len(state.memory_journal_archive) == 2
    assert len(state.player_memory_entries()) == 5


def test_journal_total_chars_and_trim():
    entries = [entry_from_text("abc"), entry_from_text("de")]
    assert journal_total_chars(entries) == 5

    pinned = entry_from_text("keep").model_copy(update={"pinned": True})
    unpinned = [entry_from_text(f"u{i}") for i in range(4)]
    trimmed = trim_memory_journal([pinned, *unpinned], max_facts=3)
    assert len(trimmed) == 3
    assert trimmed[0].text == "keep"
    assert trimmed[-1].text == "u3"
