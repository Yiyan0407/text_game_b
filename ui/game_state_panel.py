import streamlit as st

from game.models import GameState
from game.narrative_time import format_duration, narrative_time_display
from game.scenario import Scenario
from ui.memory_journal_dialog import render_memory_journal_entry
from ui.scene_map_dialog import render_scene_map_entry


def render_game_state_panel(game_state: GameState, scenario: Scenario) -> None:
    st.subheader("冒险进度")
    st.caption(
        f"🕐 {narrative_time_display(game_state)} · "
        f"已过去 {format_duration(game_state.elapsed_minutes)} · "
        f"回合 {game_state.turn_count}"
    )
    pending = [d for d in game_state.deadlines if d.status == "pending"]
    if pending:
        st.markdown("**待兑现时限**")
        for deadline in pending[:5]:
            remaining = deadline.due_at_minutes - game_state.elapsed_minutes
            if remaining < 0:
                st.caption(f"⏰ {deadline.label} · 已逾期 {format_duration(-remaining)}")
            else:
                st.caption(f"⏰ {deadline.label} · 还剩 {format_duration(remaining)}")

    player_memory_count = len(game_state.player_memory_entries())
    st.caption(
        f"记忆事实：{player_memory_count}"
        + (
            f"（活跃 {len(game_state.memory_journal)} · "
            f"归档 {len(game_state.memory_journal_archive)}）"
            if game_state.memory_journal_archive
            else ""
        )
        + f" · 章节：{len(game_state.chapter_summaries)}"
    )

    active = [q for q in game_state.active_quests if q.status == "active"]
    if active:
        st.markdown("**进行中的任务**")
        for quest in active:
            st.markdown(f"- **{quest.title}**")
            if quest.description:
                st.caption(quest.description)

    if game_state.npcs:
        with st.expander(f"已知 NPC（{len(game_state.npcs)}）", expanded=False):
            for npc in game_state.npcs:
                st.markdown(f"**{npc.name}** · {npc.attitude}")
                if npc.notes:
                    st.caption(npc.notes)

    if game_state.player_memory_entries():
        render_memory_journal_entry(game_state)
    else:
        st.caption("暂无关键记忆。")

    render_scene_map_entry(game_state, scenario)

    if game_state.chapter_summaries:
        with st.expander(f"章节回顾（{len(game_state.chapter_summaries)}）", expanded=False):
            for chapter in game_state.chapter_summaries[-3:]:
                st.markdown(chapter)
                st.divider()

    if game_state.story_summary:
        with st.expander("剧情总摘要", expanded=False):
            st.markdown(game_state.story_summary)
