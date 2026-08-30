"""创角 / 开局时的游戏选项 UI。"""

from __future__ import annotations

import streamlit as st

from game.game_config import (
    KP_GUIDANCE_LABELS,
    GameConfig,
)

KP_GUIDANCE_KEY = "game_option_kp_guidance"
BG_VALIDATION_KEY = "game_option_bg_validation"
_RENDER_GUARD_KEY = "_game_options_rendered_run_id"


def _current_script_run_id() -> str | None:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx is None:
            return None
        return str(ctx.script_run_id)
    except Exception:
        return None


def init_game_options_defaults() -> None:
    if KP_GUIDANCE_KEY not in st.session_state:
        st.session_state[KP_GUIDANCE_KEY] = "balanced"
    if BG_VALIDATION_KEY not in st.session_state:
        st.session_state[BG_VALIDATION_KEY] = True


def get_game_config_from_session() -> GameConfig:
    """从 session 读取当前选项（不渲染 widget）。"""
    init_game_options_defaults()
    return GameConfig(
        kp_guidance=st.session_state[KP_GUIDANCE_KEY],
        enable_background_validation=st.session_state[BG_VALIDATION_KEY],
    )


def render_game_options(*, show_background_validation: bool = True) -> GameConfig:
    """渲染游戏选项，返回当前选择。

    同一 Streamlit script run 内重复调用时，仅首次渲染 widget，
    后续调用只读 session（防止 DuplicateElementKey）。
    """
    run_id = _current_script_run_id()
    if run_id and st.session_state.get(_RENDER_GUARD_KEY) == run_id:
        return get_game_config_from_session()

    init_game_options_defaults()

    with st.expander("⚙️ 游戏选项", expanded=False):
        st.radio(
            "KP 引导强度",
            options=list(KP_GUIDANCE_LABELS.keys()),
            format_func=lambda key: KP_GUIDANCE_LABELS[key],
            key=KP_GUIDANCE_KEY,
            help=(
                "自由：几乎不追踪节点；平衡：KP 侧追踪进度并周期轻推；"
                "按剧本：严格追踪 beats，逾期须在叙事中引入节点要素。"
                "（剧本进度与待完成要素仅 KP 可见，不会展示给玩家。）"
            ),
        )

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

    if run_id:
        st.session_state[_RENDER_GUARD_KEY] = run_id
    return get_game_config_from_session()
