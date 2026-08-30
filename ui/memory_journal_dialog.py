"""关键记忆弹窗：按主题分组、时间线、搜索、置顶。"""

from __future__ import annotations

from collections import defaultdict

import streamlit as st

from game.memory_journal import MemoryEntry, list_memory_topics, toggle_pin_in_state
from game.models import GameState

_VIEW_TOPIC = "topic"
_VIEW_TIMELINE = "timeline"


def _has_dialog() -> bool:
    return hasattr(st, "dialog")


def _filter_entries(entries: list[MemoryEntry], query: str) -> list[MemoryEntry]:
    return [entry for entry in entries if entry.matches_query(query)]


def _timeline_key(entry: MemoryEntry) -> str:
    if entry.narrative_time:
        return entry.narrative_time
    if entry.scene_name:
        return f"{entry.time_label()} · {entry.scene_name}"
    return entry.time_label()


def _group_timeline(entries: list[MemoryEntry]) -> list[tuple[str, list[MemoryEntry]]]:
    groups: dict[str, list[MemoryEntry]] = defaultdict(list)
    for entry in entries:
        groups[_timeline_key(entry)].append(entry)
    ordered_keys = sorted(groups.keys(), reverse=True)
    return [(key, groups[key]) for key in ordered_keys]


def _render_entry_row(
    entry: MemoryEntry,
    *,
    key_prefix: str,
    game_state: GameState,
) -> None:
    meta_parts = []
    if entry.scene_name:
        meta_parts.append(entry.scene_name)
    if entry.time_label() != "时间未知":
        meta_parts.append(entry.time_label())
    meta = " · ".join(meta_parts)
    pin_label = "取消置顶" if entry.pinned else "置顶"
    col_text, col_pin = st.columns([5, 1])
    with col_text:
        tag_text = ""
        if entry.tags:
            tag_text = " · " + " · ".join(f"#{tag}" for tag in entry.tags)
        st.markdown(f"{entry.text}")
        st.caption(f"{meta}{tag_text}" if meta or tag_text else " ")
    with col_pin:
        if st.button(pin_label, key=f"{key_prefix}_pin_{entry.id}", use_container_width=True):
            toggle_pin_in_state(
                game_state.memory_journal,
                game_state.memory_journal_archive,
                entry.id,
            )
            st.rerun()


def _render_pinned_section(
    entries: list[MemoryEntry],
    *,
    key_prefix: str,
    game_state: GameState,
) -> None:
    pinned = [entry for entry in entries if entry.pinned]
    if not pinned:
        return
    st.markdown(f"**⭐ 置顶（{len(pinned)}）**")
    for entry in pinned:
        st.markdown(f"**[{entry.topic_label()}]**")
        _render_entry_row(entry, key_prefix=f"{key_prefix}_pinned", game_state=game_state)
    st.divider()


def _render_topic_view(
    entries: list[MemoryEntry],
    *,
    key_prefix: str,
    game_state: GameState,
) -> None:
    topics = list_memory_topics(entries)
    tab_labels = ["全部"] + topics
    tabs = st.tabs(tab_labels)
    for tab, label in zip(tabs, tab_labels):
        with tab:
            if label == "全部":
                subset = entries
            else:
                subset = [entry for entry in entries if entry.topic_label() == label]
            if not subset:
                st.caption(f"暂无「{label}」相关记忆。")
                continue
            for entry in reversed(subset):
                _render_entry_row(
                    entry,
                    key_prefix=f"{key_prefix}_{label}_{entry.id}",
                    game_state=game_state,
                )


def _render_timeline_view(
    entries: list[MemoryEntry],
    *,
    key_prefix: str,
    game_state: GameState,
) -> None:
    if not entries:
        st.caption("暂无关键记忆。")
        return
    for label, group in _group_timeline(entries):
        st.markdown(f"**{label}**")
        for entry in reversed(group):
            st.markdown(f"*{entry.topic_label()}*")
            _render_entry_row(
                entry,
                key_prefix=f"{key_prefix}_tl_{entry.id}",
                game_state=game_state,
            )
        st.divider()


def _render_memory_journal_content(game_state: GameState) -> None:
    all_entries = game_state.player_memory_entries()
    archive_count = len(game_state.memory_journal_archive)
    active_count = len(game_state.memory_journal)
    st.caption(
        "按主题（如人物、地点）或时间线浏览；可置顶重要情报以便潜入时快速查阅。"
        + (
            f" 共 {len(all_entries)} 条"
            + (f"（含 {archive_count} 条历史归档）" if archive_count else "")
            + f"，当前活跃 {active_count} 条供 AI 引用。"
        )
    )

    topics = list_memory_topics(all_entries)
    if topics:
        st.markdown("**已有主题**")
        st.caption(" · ".join(topics))

    active = [q for q in game_state.active_quests if q.status == "active"]
    if active:
        st.markdown("**任务速览**")
        for quest in active[:3]:
            line = f"- **{quest.title}**"
            if quest.description:
                line += f"：{quest.description}"
            st.markdown(line)
        st.divider()

    query = st.text_input(
        "搜索记忆",
        placeholder="林晓、古堡、地下、实验室…",
        key="memory_journal_search",
    )
    view = st.radio(
        "视图",
        options=[_VIEW_TOPIC, _VIEW_TIMELINE],
        format_func=lambda value: "主题" if value == _VIEW_TOPIC else "时间线",
        horizontal=True,
        key="memory_journal_view",
    )

    entries = _filter_entries(all_entries, query)
    _render_pinned_section(entries, key_prefix="memory_dialog", game_state=game_state)

    if view == _VIEW_TOPIC:
        _render_topic_view(entries, key_prefix="memory_dialog", game_state=game_state)
    else:
        _render_timeline_view(entries, key_prefix="memory_dialog", game_state=game_state)

    if game_state.chapter_summaries or game_state.story_summary:
        with st.expander("更早剧情摘要", expanded=False):
            for chapter in game_state.chapter_summaries[-2:]:
                st.markdown(chapter)
                st.divider()
            if game_state.story_summary:
                st.markdown(game_state.story_summary)


def _open_memory_journal_dialog(game_state: GameState) -> None:
    if _has_dialog():

        @st.dialog("关键记忆", width="large")
        def _dialog_body() -> None:
            _render_memory_journal_content(game_state)

        _dialog_body()
        return

    with st.expander("关键记忆（完整）", expanded=True):
        _render_memory_journal_content(game_state)


def render_memory_journal_entry(game_state: GameState) -> None:
    """侧边栏入口：按钮 + 置顶预览。"""
    all_entries = game_state.player_memory_entries()
    count = len(all_entries)
    archive_hint = ""
    if game_state.memory_journal_archive:
        archive_hint = f"（含 {len(game_state.memory_journal_archive)} 条归档）"
    if st.button(
        f"📖 关键记忆（{count}）{archive_hint}",
        use_container_width=True,
        key="open_memory_journal",
    ):
        st.session_state.memory_journal_open = True

    pinned = [entry for entry in all_entries if entry.pinned]
    if pinned:
        st.caption("⭐ 置顶预览")
        for entry in pinned[:2]:
            st.markdown(f"- [{entry.topic_label()}] {entry.text}")
    elif count:
        st.caption("可在弹窗中按主题浏览与置顶。")

    if st.session_state.get("memory_journal_open"):
        _open_memory_journal_dialog(game_state)
        st.session_state.memory_journal_open = False
