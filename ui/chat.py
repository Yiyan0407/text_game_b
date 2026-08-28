import streamlit as st

from game.kp_directive import is_kp_directive, is_kp_meta_response
from game.models import ChatMessage

AUTO_SEND_PROMPT_KEY = "auto_send_prompt"
_KP_USER_AVATAR = "🎙️"
_KP_META_AVATAR = "🎙️"
_STORY_KP_AVATAR = "🎲"


def queue_auto_send_prompt(text: str) -> None:
    st.session_state[AUTO_SEND_PROMPT_KEY] = text


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


def render_live_user_message(content: str) -> None:
    """本轮刚提交的用户消息，在写入 history 前即时展示。"""
    if is_kp_directive(content):
        _render_kp_meta_user_message(content)
        return
    with st.chat_message("user"):
        st.markdown(content)


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
    """固定在页面底部的聊天输入框（须作为页面最后一个 Streamlit 组件调用）。"""
    hint = placeholder or (
        "描述你的行动，例如：检查手机里的匿名邮件……"
        "（规则申诉以 【kp】 开头，如「【kp】刚才任务不应失败」）"
    )
    return st.chat_input(hint, disabled=disabled, key="player_chat_input")
