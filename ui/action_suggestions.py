import streamlit as st

from ui.chat import queue_auto_send_prompt


def render_action_suggestions(suggestions: list[str]) -> None:
    if not suggestions:
        return

    st.caption("💡 行动建议（点击直接发送，也可在下方输入框自行描述）")
    cols = st.columns(min(len(suggestions), 3))
    for idx, (col, action) in enumerate(zip(cols, suggestions)):
        if col.button(action, key=f"action_suggest_{idx}", use_container_width=True):
            queue_auto_send_prompt(action)
            st.rerun()
