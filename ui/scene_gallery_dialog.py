"""本局已生成场景图库弹窗。"""

from __future__ import annotations

import streamlit as st

from game.models import GameState, SceneImageRecord


def _has_dialog() -> bool:
    return hasattr(st, "dialog")


def _render_gallery_content(game_state: GameState) -> None:
    records = list(reversed(game_state.scene_image_gallery))
    if not records:
        st.info("本局尚未生成场景图。在侧边栏立绘旁点击「绘制场景」即可添加。")
        return

    st.caption(f"共 {len(records)} 张 · 按生成时间倒序")
    for idx, record in enumerate(records):
        label = record.scene_name.strip() or "未命名场景"
        turn_hint = f"第 {record.turn_count} 回合" if record.turn_count else ""
        caption = " · ".join(part for part in (label, turn_hint) if part)
        st.image(record.image_url, use_container_width=True, caption=caption)
        if idx < len(records) - 1:
            st.divider()


def _open_scene_gallery_dialog(game_state: GameState) -> None:
    title = "场景图库"

    def _body() -> None:
        _render_gallery_content(game_state)
        if st.button("关闭", key="close_scene_gallery", use_container_width=True):
            st.session_state.pop("scene_gallery_open", None)
            st.rerun()

    if _has_dialog():
        @st.dialog(title, width="large")
        def _dialog_body() -> None:
            _body()

        _dialog_body()
    else:
        with st.container(border=True):
            st.subheader(title)
            _body()


def render_scene_gallery_entry(game_state: GameState) -> None:
    count = len(game_state.scene_image_gallery)
    label = f"🖼️ 场景图库（{count}）" if count else "🖼️ 场景图库"
    if st.button(label, use_container_width=True, key="open_scene_gallery"):
        st.session_state.scene_gallery_open = True

    if st.session_state.get("scene_gallery_open"):
        _open_scene_gallery_dialog(game_state)
        st.session_state.scene_gallery_open = False
