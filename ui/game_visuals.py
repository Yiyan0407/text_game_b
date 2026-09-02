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


def render_scene_banner(game_state: GameState, scenario: Scenario) -> None:
    """主栏顶部宽幅场景图，叙事区上方像「当前镜头」。"""
    settings = get_settings()
    scene_label = game_state.current_scene.strip() or "当前场景"

    if game_state.scene_image_url:
        st.image(
            game_state.scene_image_url,
            use_container_width=True,
            caption=f"📍 {scene_label}",
        )
    else:
        st.markdown(f"### 📍 {scene_label}")

    if not settings.enable_scene_images:
        return

    if st.button(
        "🖼️ 绘制场景",
        key="generate_scene_banner",
        help="根据当前地点与模组基调生成场景氛围图",
    ):
        from chain.scene_image import generate_scene_image

        with st.spinner("绘制场景中……"):
            result = generate_scene_image(
                game_state.current_scene,
                scenario.world,
                scenario.tone,
            )
        if result.ok:
            game_state.scene_image_url = result.url
            persist_save()
            st.rerun()
        st.error(result.error or "场景图生成失败，请检查图片 API 配置。")


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


def render_sidebar_portrait_slot(*, scenario: Scenario | None = None) -> bool:
    """立绘区：有图则展示；无图且可生成则显示占位与生成按钮。"""
    profile_id, _, card = _load_current_character_card()
    if not profile_id or card is None:
        return False

    manager: ProfileManager = st.session_state.profile_manager
    has_portrait = render_portrait(
        manager,
        profile_id,
        card,
        use_container_width=True,
        show_caption=True,
    )
    world_id = scenario.world_id if scenario else card.preferred_world_id
    if has_portrait:
        render_portrait_actions(
            manager,
            profile_id,
            card,
            key_prefix="game_sidebar",
            world_id=world_id,
            compact=True,
            show_image=False,
        )
        return True

    from game.character_portrait import portrait_enabled

    if portrait_enabled():
        st.caption(f"**{card.name}**")
        render_portrait_actions(
            manager,
            profile_id,
            card,
            key_prefix="game_sidebar",
            world_id=world_id,
            compact=True,
            show_image=False,
        )
    return False
