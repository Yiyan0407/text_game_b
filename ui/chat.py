import streamlit as st

from game.models import ChatMessage


def render_chat_history(history: list[ChatMessage]) -> None:
    for msg in history:
        if msg.role == "system":
            with st.chat_message("assistant", avatar="🎲"):
                st.markdown(f"*{msg.content}*")
            continue
        role = "user" if msg.role == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(msg.content)


def render_chat_input(disabled: bool = False, placeholder: str | None = None) -> str | None:
    text = placeholder or "描述你的行动，例如：检查手机里的匿名邮件……"
    return st.chat_input(text, disabled=disabled)
