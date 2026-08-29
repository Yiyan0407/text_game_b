"""分阶段流式 UI 辅助。"""

from collections.abc import Callable, Iterator

import streamlit as st

from game.results import TurnResult
from ui.loading import LoadingPlaceholder


def render_streaming_markdown(
    text_stream: Iterator[str],
    *,
    loading: LoadingPlaceholder | None = None,
    loading_message: str = "KP 撰写叙事中……",
    on_tools_ready: Callable[[], None] | None = None,
) -> str:
    """逐块渲染 Markdown，比 st.write_stream 更稳定地触发 UI 刷新。"""
    box = st.empty()
    if loading:
        loading.show(loading_message)
    else:
        box.markdown("*⏳ KP 撰写叙事中……*")

    full = ""
    tools_notified = False
    started = False

    for chunk in text_stream:
        if not tools_notified and on_tools_ready:
            on_tools_ready()
            tools_notified = True
        if not started:
            if loading:
                loading.clear()
            started = True
        full += chunk
        box.markdown(full + "▌")

    if on_tools_ready and not tools_notified:
        on_tools_ready()

    if not started:
        if loading:
            loading.clear()
        box.markdown("*（KP 暂无回复）*")
        return ""

    box.markdown(full)
    return full


def render_phased_turn(
    pre_tool_events: list[str],
    run_state_phase: Callable[[], list[str]],
    text_stream: Iterator[str],
    *,
    loading: LoadingPlaceholder | None = None,
    kp_meta: bool = False,
) -> tuple[list[str], str]:
    """分阶段展示：系统结算 → KP 叙事流（分开展示）。"""
    if pre_tool_events:
        from ui.chat import render_tool_events_live

        render_tool_events_live(pre_tool_events)

    if loading:
        loading.show("KP 沟通处理中……" if kp_meta else "准备叙事……")
    state_events = run_state_phase()
    if loading:
        loading.clear()

    if state_events:
        from ui.chat import render_tool_events_live

        render_tool_events_live(state_events)

    from ui.chat import kp_story_chat_message

    with kp_story_chat_message(kp_meta=kp_meta):
        if kp_meta:
            st.caption("主持人回复")
        else:
            st.caption("KP · 叙事")
        full = render_streaming_markdown(
            text_stream,
            loading=loading,
            loading_message="KP 回复中……" if kp_meta else "KP 撰写叙事中……",
        )
    return state_events, full


def finalize_streaming_turn(
    full_response: str,
    *,
    run_item_sync_phase: Callable[[str], list[str]],
    run_memory_finalize: Callable[[], bool],
    finish_turn: Callable[[str], TurnResult],
    kp_meta: bool = False,
) -> TurnResult:
    """流式回合收尾：物品同步 → 记忆整理 → 行动建议。"""
    if kp_meta:
        item_events = run_item_sync_phase(full_response or "")
        run_memory_finalize()
        return finish_turn(full_response or "")

    with st.spinner("同步物品与装备中……"):
        item_events = run_item_sync_phase(full_response or "")
    if item_events:
        from ui.chat import render_tool_events_live

        render_tool_events_live(item_events)

    with st.spinner("整理冒险记忆中……"):
        summary_updated = run_memory_finalize()
    with st.spinner("生成行动建议中……"):
        turn = finish_turn(full_response or "")
    if summary_updated:
        turn.summary_updated = True
    return turn
