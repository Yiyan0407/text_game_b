import streamlit as st

from game.models import GameState


def render_game_state_panel(game_state: GameState) -> None:
    st.subheader("冒险进度")
    st.caption(
        f"回合：{game_state.turn_count} · "
        f"记忆事实：{len(game_state.memory_facts)} · "
        f"章节：{len(game_state.chapter_summaries)}"
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

    if game_state.memory_facts:
        with st.expander(f"关键记忆（{len(game_state.memory_facts)}）", expanded=False):
            for fact in game_state.memory_facts[-12:]:
                st.markdown(f"- {fact}")

    if game_state.chapter_summaries:
        with st.expander(f"章节回顾（{len(game_state.chapter_summaries)}）", expanded=False):
            for chapter in game_state.chapter_summaries[-3:]:
                st.markdown(chapter)
                st.divider()

    if game_state.story_summary:
        with st.expander("剧情总摘要", expanded=False):
            st.markdown(game_state.story_summary)
