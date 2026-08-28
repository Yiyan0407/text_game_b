"""创角 / 开局时的游戏选项 UI。"""

from __future__ import annotations

import streamlit as st

from game.game_config import (
    KP_GUIDANCE_LABELS,
    GameConfig,
    KpGuidance,
)

KP_GUIDANCE_KEY = "game_option_kp_guidance"
BG_VALIDATION_KEY = "game_option_bg_validation"


def init_game_options_defaults() -> None:
    if KP_GUIDANCE_KEY not in st.session_state:
        st.session_state[KP_GUIDANCE_KEY] = "balanced"
    if BG_VALIDATION_KEY not in st.session_state:
        st.session_state[BG_VALIDATION_KEY] = True


def render_game_options(*, show_background_validation: bool = True) -> GameConfig:
    """渲染游戏选项，返回当前选择。"""
    init_game_options_defaults()

    with st.expander("⚙️ 游戏选项", expanded=False):
        guidance: KpGuidance = st.radio(
            "KP 引导强度",
            options=list(KP_GUIDANCE_LABELS.keys()),
            format_func=lambda key: KP_GUIDANCE_LABELS[key],
            key=KP_GUIDANCE_KEY,
            help=(
                "自由：几乎不主动指路；平衡：开局与迷茫时轻量提示；"
                "按剧本：更积极铺设模组关键节点与事件。"
            ),
        )

        enable_bg_validation = True
        if show_background_validation:
            enable_bg_validation = st.checkbox(
                "启用背景平衡审核",
                key=BG_VALIDATION_KEY,
                help="关闭后跳过「开局无敌/满级/神器」等审核，适合想放飞自我的玩家。",
            )
            if not enable_bg_validation:
                st.warning(
                    "已关闭背景审核：超模背景可能导致开局体验失衡，"
                    "KP 仍会尽量按规则叙事，但不保证完全兼容。"
                )

    return GameConfig(
        kp_guidance=guidance,
        enable_background_validation=enable_bg_validation,
    )
