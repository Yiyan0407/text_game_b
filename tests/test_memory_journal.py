from game.memory_journal import (
    DEFAULT_TOPIC,
    MemoryEntry,
    entry_from_text,
    normalize_topic,
    resolve_topic,
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
