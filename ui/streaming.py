"""分阶段流式 UI 辅助。"""

from collections.abc import Callable, Iterator

import streamlit as st

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
    state_events: list[str],
    text_stream: Iterator[str],
    *,
    loading: LoadingPlaceholder | None = None,
) -> str:
    """分阶段展示：机械事件 → 状态同步 → 叙事流。"""
    if pre_tool_events:
        from ui.chat import render_tool_events_live

        render_tool_events_live(pre_tool_events)

    if state_events:
        if loading:
            loading.show("同步世界状态中……")
        from ui.chat import render_tool_events_live

        render_tool_events_live(state_events)
        if loading:
            loading.clear()

    return render_streaming_markdown(
        text_stream,
        loading=loading,
        loading_message="KP 撰写叙事中……",
    )
