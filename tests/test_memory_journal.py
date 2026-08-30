from game.memory_journal import (
    DEFAULT_TOPIC,
    MemoryEntry,
    entry_from_text,
    is_trivial_memory,
    normalize_topic,
    player_memory_entries,
    resolve_topic,
    trim_memory_journal_with_archive,
)


def test_normalize_topic():
    assert normalize_topic("  任务线索  ") == "任务线索"
    assert normalize_topic("") == DEFAULT_TOPIC


def test_resolve_topic_uses_explicit():
    assert resolve_topic(explicit="人物") == "人物"
    assert resolve_topic(explicit="quest") == "任务"


def test_resolve_topic_defaults_without_explicit():
    assert resolve_topic() == DEFAULT_TOPIC
    assert resolve_topic(explicit="") == DEFAULT_TOPIC


def test_entry_from_text_uses_explicit_topic():
    entry = entry_from_text("老周答应一起查看压缩包", topic="人物")
    assert entry.topic == "人物"


def test_entry_from_text_defaults_topic():
    entry = entry_from_text("某条线索")
    assert entry.topic == DEFAULT_TOPIC


def test_memory_entry_auto_id():
    entry = MemoryEntry(text="测试")
    assert entry.id
    assert entry.topic == DEFAULT_TOPIC


def test_player_memory_entries_merges_archive_and_journal():
    journal = [entry_from_text("活跃记忆")]
    archive = [entry_from_text("归档记忆")]
    combined = player_memory_entries(journal, archive)
    assert len(combined) == 2
    assert {entry.text for entry in combined} == {"活跃记忆", "归档记忆"}


def test_trim_memory_journal_with_archive():
    entries = [entry_from_text(f"事实{i}") for i in range(4)]
    kept, dropped = trim_memory_journal_with_archive(entries, max_facts=2)
    assert len(kept) == 2
    assert len(dropped) == 2
    assert kept[-1].text == "事实3"
    assert dropped[0].text == "事实0"


def test_is_trivial_memory_filters_check_failures():
    assert is_trivial_memory("尝试「攀爬外墙」失败（敏捷检定 7 vs DC 18）")
    assert is_trivial_memory("潜入/潜行尝试失败，现场警戒可能已提高")
    assert not is_trivial_memory("铁匠答应明天交货，逾期则不再合作")
