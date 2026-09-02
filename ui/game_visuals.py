"""对局内场景图与角色立绘的沉浸式布局。"""

from __future__ import annotations

import streamlit as st

from config.settings import get_settings
from game.character_portrait import resolve_portrait_path
from game.models import GameState
from game.profile import ProfileManager
from game.scenario import Scenario
from game.session import persist_save
from ui.character_portrait import render_portrait, render_portrait_actions
from ui.scene_gallery_dialog import render_scene_gallery_entry


def render_current_scene_label(game_state: GameState) -> None:
    scene_label = game_state.current_scene.strip() or "当前场景"
    st.markdown(f"**📍 {scene_label}**")


def _load_current_character_card():
    profile_id = st.session_state.get("current_profile_id")
    character_id = st.session_state.get("current_character_id")
    if not profile_id or not character_id:
        return None, None, None
    manager: ProfileManager = st.session_state.profile_manager
    try:
        card = manager.load_character_card(profile_id, character_id)
    except FileNotFoundError:
        return profile_id, character_id, None
    return profile_id, character_id, card


def _render_sidebar_scene_slot(game_state: GameState, scenario: Scenario) -> None:
    settings = get_settings()
    scene_label = game_state.current_scene.strip() or "当前场景"

    if game_state.scene_image_url:
        st.image(
            game_state.scene_image_url,
            use_container_width=True,
            caption=f"📍 {scene_label}",
        )
    else:
        st.caption("📍 " + scene_label)
        st.caption("（尚未绘制场景图）")

    if not settings.enable_scene_images:
        return

    if st.button(
        "🖼️ 绘制场景",
        key="generate_scene_sidebar",
        use_container_width=True,
        help="根据当前地点与模组基调生成场景氛围图",
    ):
        from chain.scene_image import generate_scene_image

        with st.spinner("绘制场景中……"):
            result = generate_scene_image(
                game_state.current_scene,
                scenario.world,
                scenario.tone,
            )
        if result.ok and result.url:
            game_state.register_scene_image(game_state.current_scene, result.url)
            persist_save()
            st.rerun()
        st.error(result.error or "场景图生成失败，请检查图片 API 配置。")


def render_sidebar_visual_panel(*, game_state: GameState, scenario: Scenario | None) -> bool:
    """侧边栏：立绘与当前场景图并排；返回是否有立绘。"""
    profile_id, _, card = _load_current_character_card()
    has_portrait = False
    world_id = scenario.world_id if scenario else ""

    if card and profile_id and scenario:
        manager: ProfileManager = st.session_state.profile_manager
        portrait_col, scene_col = st.columns(2)
        with portrait_col:
            has_portrait = render_portrait(
                manager,
                profile_id,
                card,
                use_container_width=True,
                show_caption=True,
            )
            if not has_portrait:
                st.caption(card.name)
            render_portrait_actions(
                manager,
                profile_id,
                card,
                key_prefix="game_sidebar",
                world_id=world_id or card.preferred_world_id,
                compact=True,
                show_image=False,
            )
        with scene_col:
            _render_sidebar_scene_slot(game_state, scenario)
    elif scenario:
        _render_sidebar_scene_slot(game_state, scenario)

    render_scene_gallery_entry(game_state)
    return has_portrait


def render_sidebar_portrait_slot(*, scenario: Scenario | None = None) -> bool:
    """兼容旧调用：仅立绘区。"""
    game_state: GameState | None = st.session_state.get("game_state")
    if game_state is None:
        return False
    return render_sidebar_visual_panel(game_state=game_state, scenario=scenario)
