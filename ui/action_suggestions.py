import streamlit as st

from ui.chat import seed_chat_draft


def render_action_suggestions(suggestions: list[str]) -> None:
    if not suggestions:
        return

    st.caption("💡 行动建议（点击填入下方输入框，可修改后再发送）")
    cols = st.columns(min(len(suggestions), 3))
    for idx, (col, action) in enumerate(zip(cols, suggestions)):
        if col.button(action, key=f"action_suggest_{idx}", use_container_width=True):
            seed_chat_draft(action)
            st.rerun()
