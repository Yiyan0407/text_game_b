import streamlit as st


def render_action_suggestions(suggestions: list[str]) -> str | None:
    if not suggestions:
        return None

    st.caption("💡 行动建议（点击直接发送）")
    cols = st.columns(min(len(suggestions), 3))
    for idx, (col, action) in enumerate(zip(cols, suggestions)):
        if col.button(action, key=f"action_suggest_{idx}", use_container_width=True):
            return action
    return None
