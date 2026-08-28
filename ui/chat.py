import streamlit as st

from game.models import ChatMessage

CHAT_DRAFT_KEY = "chat_draft"


def seed_chat_draft(text: str) -> None:
    st.session_state[CHAT_DRAFT_KEY] = text


def clear_chat_draft() -> None:
    st.session_state[CHAT_DRAFT_KEY] = ""


def format_tool_event_content(content: str) -> str:
    text = str(content).strip()
    if text.startswith("🎲 "):
        return text[2:].strip()
    return text


def render_tool_events_live(tool_events: list[str]) -> None:
    for event in tool_events:
        text = format_tool_event_content(event)
        if not text:
            continue
        with st.chat_message("assistant", avatar="🎲"):
            st.markdown(f"*{text}*")


def render_chat_history(history: list[ChatMessage]) -> None:
    for msg in history:
        if msg.role == "system":
            with st.chat_message("assistant", avatar="🎲"):
                st.markdown(f"*{format_tool_event_content(msg.content)}*")
            continue
        role = "user" if msg.role == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(msg.content)


def render_chat_input(disabled: bool = False, placeholder: str | None = None) -> str | None:
    hint = placeholder or "描述你的行动，例如：检查手机里的匿名邮件……"
    if CHAT_DRAFT_KEY not in st.session_state:
        st.session_state[CHAT_DRAFT_KEY] = ""

    with st.form("player_action_form", clear_on_submit=True):
        draft = st.text_area(
            "行动输入",
            key=CHAT_DRAFT_KEY,
            height=72,
            placeholder=hint,
            disabled=disabled,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "发送",
            disabled=disabled,
            use_container_width=True,
            type="primary",
        )

    if submitted and not disabled:
        text = draft.strip()
        if text:
            return text
    return None
