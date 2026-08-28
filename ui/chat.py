import streamlit as st

from game.kp_directive import is_kp_directive, is_kp_meta_response
from game.models import ChatMessage

CHAT_DRAFT_KEY = "chat_draft"
_KP_USER_AVATAR = "🎙️"
_KP_META_AVATAR = "🎙️"
_STORY_KP_AVATAR = "🎲"


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
        with st.chat_message("assistant", avatar=_STORY_KP_AVATAR):
            st.markdown(f"*{text}*")


def _render_kp_meta_user_message(content: str) -> None:
    with st.chat_message("user", avatar=_KP_USER_AVATAR):
        st.caption("出戏沟通 · 主持人频道")
        st.markdown(content)


def _render_kp_meta_assistant_message(content: str) -> None:
    with st.chat_message("assistant", avatar=_KP_META_AVATAR):
        st.caption("主持人回复")
        st.markdown(content)


def render_chat_history(history: list[ChatMessage]) -> None:
    for msg in history:
        if msg.role == "system":
            with st.chat_message("assistant", avatar=_STORY_KP_AVATAR):
                st.markdown(f"*{format_tool_event_content(msg.content)}*")
            continue
        if msg.role == "user" and is_kp_directive(msg.content):
            _render_kp_meta_user_message(msg.content)
            continue
        if msg.role == "assistant" and is_kp_meta_response(msg.content):
            _render_kp_meta_assistant_message(msg.content)
            continue
        role = "user" if msg.role == "user" else "assistant"
        avatar = _STORY_KP_AVATAR if role == "assistant" else None
        with st.chat_message(role, avatar=avatar):
            st.markdown(msg.content)


def render_chat_input(disabled: bool = False, placeholder: str | None = None) -> str | None:
    hint = placeholder or (
        "描述你的行动，例如：检查手机里的匿名邮件……"
        "（规则申诉以 【kp】 开头，如「【kp】刚才任务不应失败」）"
    )
    initial = str(st.session_state.get(CHAT_DRAFT_KEY, ""))

    with st.form("player_action_form", clear_on_submit=True):
        user_text = st.text_area(
            "行动输入",
            value=initial,
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
        text = user_text.strip()
        if text:
            clear_chat_draft()
            return text
    return None
