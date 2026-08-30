"""结构化关键记忆：按主题分组、时间线、置顶。"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_TOPIC = "综合"

_LEGACY_CATEGORY_TO_TOPIC: dict[str, str] = {
    "quest": "任务",
    "location": "地点",
    "npc": "人物",
    "world": "世界观",
    "clue": "线索",
    "threat": "警告",
    "other": DEFAULT_TOPIC,
}


class MemoryEntry(BaseModel):
    id: str = ""
    text: str = ""
    topic: str = DEFAULT_TOPIC
    turn_count: int = 0
    elapsed_minutes: int = 0
    narrative_time: str = ""
    scene_id: str = ""
    scene_name: str = ""
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False
    recorded_at: str = ""

    @field_validator("text", "narrative_time", "scene_id", "scene_name", mode="before")
    @classmethod
    def _strip_text(cls, value) -> str:
        return str(value or "").strip()

    @field_validator("topic", mode="before")
    @classmethod
    def _normalize_topic_field(cls, value) -> str:
        return normalize_topic(str(value or ""))

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value) -> list[str]:
        if not value:
            return []
        if isinstance(value, str):
            return [part.strip() for part in re.split(r"[,，、]", value) if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_category(cls, data):
        if not isinstance(data, dict):
            return data
        if data.get("topic"):
            return data
        legacy = str(data.get("category", "")).strip().lower()
        if legacy:
            data = dict(data)
            data["topic"] = _LEGACY_CATEGORY_TO_TOPIC.get(legacy, DEFAULT_TOPIC)
        return data

    @model_validator(mode="after")
    def _ensure_id(self) -> MemoryEntry:
        if not self.id.strip():
            object.__setattr__(self, "id", uuid.uuid4().hex[:12])
        if not self.topic.strip():
            object.__setattr__(self, "topic", DEFAULT_TOPIC)
        return self

    def topic_label(self) -> str:
        return self.topic or DEFAULT_TOPIC

    def time_label(self) -> str:
        if self.narrative_time:
            return self.narrative_time
        if self.elapsed_minutes > 0:
            return f"第{self.elapsed_minutes // (24 * 60) + 1}天 +{self.elapsed_minutes % (24 * 60)}分"
        return "时间未知"

    def matches_query(self, query: str) -> bool:
        needle = query.strip().casefold()
        if not needle:
            return True
        haystacks = [
            self.text,
            self.topic,
            self.scene_name,
            self.narrative_time,
            " ".join(self.tags),
        ]
        return any(needle in part.casefold() for part in haystacks if part)


def normalize_topic(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned:
        return DEFAULT_TOPIC
    return cleaned[:24]


def resolve_topic(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        legacy = explicit.strip().lower()
        if legacy in _LEGACY_CATEGORY_TO_TOPIC:
            return _LEGACY_CATEGORY_TO_TOPIC[legacy]
        normalized = normalize_topic(explicit)
        if normalized != DEFAULT_TOPIC or explicit.strip() == DEFAULT_TOPIC:
            return normalized
    return DEFAULT_TOPIC


def entry_from_text(
    text: str,
    *,
    topic: str | None = None,
    tags: list[str] | None = None,
    turn_count: int = 0,
    elapsed_minutes: int = 0,
    narrative_time: str = "",
    scene_id: str = "",
    scene_name: str = "",
    existing_topics: list[str] | None = None,
    npc_names: list[str] | None = None,
    quest_titles: list[str] | None = None,
) -> MemoryEntry:
    cleaned = text.strip()
    resolved_topic = resolve_topic(topic)
    return MemoryEntry(
        text=cleaned,
        topic=resolved_topic,
        tags=list(tags or []),
        turn_count=turn_count,
        elapsed_minutes=elapsed_minutes,
        narrative_time=narrative_time,
        scene_id=scene_id,
        scene_name=scene_name,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )


def migrate_legacy_facts(facts: list[str]) -> list[MemoryEntry]:
    entries: list[MemoryEntry] = []
    for fact in facts:
        cleaned = str(fact).strip()
        if not cleaned:
            continue
        entries.append(entry_from_text(cleaned))
    return entries


def coerce_memory_patch_item(value) -> MemoryEntry | None:
    if isinstance(value, MemoryEntry):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        return entry_from_text(cleaned)
    if isinstance(value, dict):
        if value.get("text") or value.get("fact"):
            if value.get("id"):
                return MemoryEntry.model_validate(value)
            text = str(value.get("text") or value.get("fact") or "").strip()
            if not text:
                return None
            topic_raw = str(value.get("topic") or value.get("category") or "").strip()
            legacy = topic_raw.lower()
            if legacy in _LEGACY_CATEGORY_TO_TOPIC:
                topic_raw = _LEGACY_CATEGORY_TO_TOPIC[legacy]
            return entry_from_text(
                text,
                topic=topic_raw or None,
                tags=value.get("tags"),
                turn_count=int(value.get("turn_count", 0) or 0),
                elapsed_minutes=int(value.get("elapsed_minutes", 0) or 0),
                narrative_time=str(value.get("narrative_time", "")).strip(),
                scene_id=str(value.get("scene_id", "")).strip(),
                scene_name=str(value.get("scene_name", "")).strip(),
            ).model_copy(update={"pinned": bool(value.get("pinned", False))})
        return None
    return None


def normalize_memory_journal(value) -> list[MemoryEntry]:
    if not value:
        return []
    if isinstance(value, list):
        entries: list[MemoryEntry] = []
        for item in value:
            entry = coerce_memory_patch_item(item)
            if entry is not None:
                entries.append(entry)
        return entries
    return []


def list_memory_topics(entries: list[MemoryEntry]) -> list[str]:
    """按最近活跃排序的主题列表。"""
    latest: dict[str, int] = {}
    for entry in entries:
        topic = entry.topic_label()
        score = max(entry.turn_count, entry.elapsed_minutes)
        latest[topic] = max(latest.get(topic, 0), score)
    return sorted(latest.keys(), key=lambda name: (latest[name], name), reverse=True)


def group_by_topic(entries: list[MemoryEntry]) -> dict[str, list[MemoryEntry]]:
    groups: dict[str, list[MemoryEntry]] = {}
    for entry in entries:
        topic = entry.topic_label()
        groups.setdefault(topic, []).append(entry)
    return groups


def facts_for_prompt(entries: list[MemoryEntry], *, limit: int = 20) -> list[str]:
    """置顶优先，再补足最近未置顶条目。"""
    if not entries:
        return []
    pinned = [entry for entry in entries if entry.pinned]
    unpinned = [entry for entry in entries if not entry.pinned]
    selected = list(pinned)
    remaining = max(0, limit - len(selected))
    if remaining:
        selected.extend(unpinned[-remaining:])
    return [entry.text for entry in selected]


def format_topics_for_prompt(entries: list[MemoryEntry]) -> str:
    topics = list_memory_topics(entries)
    if not topics:
        return "（尚无主题，可新建如「林晓」「古堡」「B2实验室」等简短主题名）"
    return "、".join(topics)


def toggle_pin(entries: list[MemoryEntry], entry_id: str) -> bool:
    for index, entry in enumerate(entries):
        if entry.id == entry_id:
            entries[index] = entry.model_copy(update={"pinned": not entry.pinned})
            return True
    return False


def find_entry(entries: list[MemoryEntry], entry_id: str) -> MemoryEntry | None:
    for entry in entries:
        if entry.id == entry_id:
            return entry
    return None


def journal_total_chars(entries: list[MemoryEntry]) -> int:
    return sum(len(entry.text) for entry in entries)


_TRIVIAL_MEMORY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"尝试「.+」失败（.+检定"),
    re.compile(r"检定 \d+ vs DC \d+"),
    re.compile(r"^社交尝试「.+」失败"),
    re.compile(r"^潜入/潜行尝试失败"),
    re.compile(r"^向他人学习「.+」失败"),
    re.compile(r"^(观察|搜索|查看|检查|询问).{0,12}$"),
)


def is_trivial_memory(text: str) -> bool:
    """过滤不应进入关键记忆的琐碎/临时条目。"""
    cleaned = text.strip()
    if len(cleaned) < 4:
        return True
    for pattern in _TRIVIAL_MEMORY_PATTERNS:
        if pattern.search(cleaned):
            return True
    return False


def format_entries_for_compress(entries: list[MemoryEntry]) -> str:
    """按主题格式化，供记忆压缩 prompt 使用。"""
    if not entries:
        return "（无）"
    lines: list[str] = []
    for topic, group in group_by_topic(entries).items():
        lines.append(f"【主题：{topic}】")
        for entry in sorted(group, key=lambda item: (item.turn_count, item.elapsed_minutes)):
            meta = entry.time_label()
            if entry.scene_name:
                meta = f"{meta} · {entry.scene_name}"
            lines.append(f"- {entry.text}（{meta}）")
        lines.append("")
    return "\n".join(lines).strip()


def merge_compressed_entries(
    originals: list[MemoryEntry],
    compressed: list[MemoryEntry],
) -> list[MemoryEntry]:
    """为压缩结果补全时间/场景元数据（取原组最早 turn、最新场景）。"""
    groups = group_by_topic(originals)
    merged: list[MemoryEntry] = []
    for entry in compressed:
        if not entry.text.strip():
            continue
        source = groups.get(entry.topic_label(), [])
        turn_counts = [item.turn_count for item in source if item.turn_count > 0]
        elapsed_values = [item.elapsed_minutes for item in source if item.elapsed_minutes > 0]
        turn_count = min(turn_counts) if turn_counts else 0
        elapsed = min(elapsed_values) if elapsed_values else 0
        narrative_time = next(
            (item.narrative_time for item in reversed(source) if item.narrative_time),
            "",
        )
        scene_id = next((item.scene_id for item in reversed(source) if item.scene_id), "")
        scene_name = next((item.scene_name for item in reversed(source) if item.scene_name), "")
        merged.append(
            entry.model_copy(
                update={
                    "turn_count": turn_count or entry.turn_count,
                    "elapsed_minutes": elapsed or entry.elapsed_minutes,
                    "narrative_time": narrative_time or entry.narrative_time,
                    "scene_id": scene_id or entry.scene_id,
                    "scene_name": scene_name or entry.scene_name,
                    "pinned": False,
                }
            )
        )
    return merged


def trim_memory_journal(entries: list[MemoryEntry], max_facts: int) -> list[MemoryEntry]:
    """置顶保留，未置顶保留最新若干条。"""
    kept, _ = trim_memory_journal_with_archive(entries, max_facts)
    return kept


def trim_memory_journal_with_archive(
    entries: list[MemoryEntry],
    max_facts: int,
) -> tuple[list[MemoryEntry], list[MemoryEntry]]:
    """裁剪活跃记忆，返回 (保留, 应移入归档的条目)。"""
    if len(entries) <= max_facts:
        return entries, []
    pinned = [entry for entry in entries if entry.pinned]
    unpinned = [entry for entry in entries if not entry.pinned]
    keep_unpinned = max(0, max_facts - len(pinned))
    if keep_unpinned:
        dropped = unpinned[:-keep_unpinned]
        kept = pinned + unpinned[-keep_unpinned:]
    else:
        dropped = unpinned
        kept = pinned
    return kept, dropped


def player_memory_entries(
    journal: list[MemoryEntry],
    archive: list[MemoryEntry] | None = None,
) -> list[MemoryEntry]:
    """玩家可见的完整记忆：归档原文 + 当前活跃条目（按 id 去重）。"""
    seen: set[str] = set()
    combined: list[MemoryEntry] = []
    for entry in list(archive or []) + list(journal):
        entry_id = entry.id.strip()
        if entry_id and entry_id in seen:
            continue
        if entry_id:
            seen.add(entry_id)
        combined.append(entry)
    return combined


def toggle_pin_in_state(
    journal: list[MemoryEntry],
    archive: list[MemoryEntry],
    entry_id: str,
) -> bool:
    if toggle_pin(journal, entry_id):
        return True
    return toggle_pin(archive, entry_id)
