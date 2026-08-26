from collections.abc import Callable, Iterator

import streamlit as st


def render_streaming_markdown(
    text_stream: Iterator[str],
    *,
    on_tools_ready: Callable[[], None] | None = None,
) -> str:
    """逐块渲染 Markdown，比 st.write_stream 更稳定地触发 UI 刷新。"""
    box = st.empty()
    full = ""
    tools_notified = False

    for chunk in text_stream:
        if not tools_notified and on_tools_ready:
            on_tools_ready()
            tools_notified = True
        full += chunk
        box.markdown(full + "▌")

    if on_tools_ready and not tools_notified:
        on_tools_ready()

    box.markdown(full)
    return full
