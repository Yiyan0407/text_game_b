"""场景地图弹窗：Cytoscape 交互拓扑图 + 已访问地点列表。"""

from __future__ import annotations

import streamlit as st

from game.models import GameState
from game.scene_map import group_visited_by_scope, prepare_map_display, render_cytoscape_html, scope_display_label
from game.scenario import Scenario


def _has_dialog() -> bool:
    return hasattr(st, "dialog")


def _refresh_map(game_state: GameState, scenario: Scenario) -> bool:
    orchestrator = st.session_state.get("orchestrator")
    if orchestrator is None:
        st.warning("无法刷新：游戏编排器未就绪。")
        return False
    history = list(st.session_state.get("messages") or [])
    with st.spinner("AI 正在整理地图拓扑……"):
        updated = orchestrator.refresh_scene_map(game_state, scenario, history)
    if updated:
        from game.session import persist_save

        persist_save()
        st.toast("场景地图已更新")
        return True
    st.warning("地图更新失败或未返回有效数据，已保留原有地图。")
    return False


def _render_map_content(game_state: GameState, scenario: Scenario) -> None:
    graph, visited_records = prepare_map_display(game_state, scenario)
    explored = len(visited_records)
    st.caption(
        f"当前位置：**{game_state.current_scene}** · "
        f"已探索 {explored} 处 · 可缩放拖拽"
    )

    if graph and not graph.is_empty():
        st.iframe(render_cytoscape_html(graph), height=440)
    else:
        st.info("继续冒险后，地图会随场景探索自动更新。")

    if visited_records:
        st.markdown("**已访问地点**")
        grouped = group_visited_by_scope(list(reversed(visited_records)))
        multi_scope = len(grouped) > 1 or (
            len(grouped) == 1 and grouped[0][0] != ""
        )
        for scope, records in grouped:
            if multi_scope and scope:
                st.caption(f"▸ {scope_display_label(scope, scenario)}（{scope}）")
            for record in records:
                turn = (
                    "开场"
                    if record.first_seen_turn <= 0
                    else f"第 {record.first_seen_turn} 回合"
                )
                marker = "📍 " if record.scene_id == game_state.scene_id else "· "
                st.markdown(
                    f"{marker}**{record.scene_name}** · {turn}"
                )

    col_refresh, col_close = st.columns(2)
    with col_refresh:
        if st.button("🔄 刷新地图", key="scene_map_refresh", use_container_width=True):
            _refresh_map(game_state, scenario)
            st.session_state.scene_map_open = True
            st.rerun()
    with col_close:
        if st.button("关闭", key="scene_map_close", use_container_width=True):
            st.session_state.scene_map_open = False
            st.rerun()


def _open_scene_map_dialog(game_state: GameState, scenario: Scenario) -> None:
    if _has_dialog():

        @st.dialog("场景地图", width="large")
        def _dialog_body() -> None:
            _render_map_content(game_state, scenario)

        _dialog_body()
        return

    with st.expander("场景地图（完整）", expanded=True):
        _render_map_content(game_state, scenario)


def render_scene_map_entry(game_state: GameState, scenario: Scenario) -> None:
    """侧边栏入口：按钮 + 当前位置预览。"""
    _, visited_records = prepare_map_display(game_state, scenario)
    count = len(visited_records)
    label = f"🗺️ 场景地图（{count}）" if count else "🗺️ 场景地图"
    if st.button(label, use_container_width=True, key="open_scene_map"):
        st.session_state.scene_map_open = True

    st.caption(f"📍 {game_state.current_scene}")

    if st.session_state.get("scene_map_open"):
        _open_scene_map_dialog(game_state, scenario)
        st.session_state.scene_map_open = False
