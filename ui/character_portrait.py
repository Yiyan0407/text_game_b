"""角色立绘展示与手动刷新。"""

from __future__ import annotations

import streamlit as st

from game.character_portrait import (
    generate_and_save_portrait,
    portrait_enabled,
    resolve_portrait_path,
)
from game.profile import CharacterCard, ProfileManager


def render_portrait(
    manager: ProfileManager,
    profile_id: str,
    card: CharacterCard,
    *,
    width: int | None = None,
    use_container_width: bool = False,
    show_caption: bool = True,
) -> bool:
    """展示立绘；有文件返回 True。"""
    path = resolve_portrait_path(manager, profile_id, card)
    if path is None:
        return False
    st.image(
        str(path),
        width=width,
        use_container_width=use_container_width if width is None else False,
        caption=card.name if show_caption else None,
    )
    return True


def render_portrait_actions(
    manager: ProfileManager,
    profile_id: str,
    card: CharacterCard,
    *,
    key_prefix: str,
    world_id: str = "",
    compact: bool = False,
    show_image: bool = True,
) -> None:
    """渲染立绘区与「生成/刷新」按钮。"""
    has_portrait = False
    if show_image:
        has_portrait = render_portrait(
            manager,
            profile_id,
            card,
            width=160 if compact else 320,
            show_caption=not compact,
        )
    else:
        has_portrait = resolve_portrait_path(manager, profile_id, card) is not None

    if show_image and not has_portrait:
        st.caption("尚无立绘")

    enabled = portrait_enabled()
    label = "重新生成立绘" if has_portrait else "生成立绘"
    help_text = (
        "根据当前背景、装备与战役经历重新生成角色立绘。"
        if has_portrait
        else "根据角色背景生成全身立绘。"
    )
    if not enabled:
        st.caption(
            "立绘生成未启用：请配置 SEEDREAM_API_KEY 或 OPENAI_API_KEY，"
            "并保持 ENABLE_CHARACTER_PORTRAITS=true。"
        )
        return

    if st.button(
        label,
        key=f"{key_prefix}_portrait_refresh_{card.card_id}",
        use_container_width=True,
        help=help_text,
    ):
        with st.spinner("正在生成角色立绘，请稍候……"):
            result = generate_and_save_portrait(
                manager,
                profile_id,
                card,
                world_id=world_id or card.preferred_world_id,
            )
        if result.ok and result.card.portrait_file:
            st.rerun()
        st.warning(result.error or "立绘生成失败，请检查图片 API 配置或稍后重试。")
