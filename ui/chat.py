import re

import streamlit as st

from game.kp_directive import is_kp_directive, is_kp_meta_response
from game.models import ChatMessage
from ui.system_events import CompactSystemView, compact_system_events, format_tool_event_content

AUTO_SEND_PROMPT_KEY = "auto_send_prompt"
_KP_USER_AVATAR = "🎙️"
_KP_META_AVATAR = "🎙️"
_STORY_KP_AVATAR = "🎲"
_SYSTEM_AVATAR = "⚙️"
_TAG_LINE_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)


def queue_auto_send_prompt(text: str) -> None:
    st.session_state[AUTO_SEND_PROMPT_KEY] = text


def _system_caption(content: str) -> str:
    return compact_system_events([content]).caption


def _format_tagged_markdown(line: str) -> str:
    match = _TAG_LINE_RE.match(line.strip())
    if not match:
        return line
    tag, body = match.group(1), match.group(2).strip()
    if not body:
        return f"**[{tag}]**"
    return f"**[{tag}]** {body}"


def _render_compact_system_view(view: CompactSystemView) -> None:
    if not view.highlights and not view.summary and not view.details:
        return
    with st.chat_message("assistant", avatar=_SYSTEM_AVATAR):
        st.caption(view.caption)
        for line in view.highlights:
            st.markdown(_format_tagged_markdown(line))
        if view.summary:
            st.markdown(f"*{view.summary}*")
        if view.details and not view.show_expander:
            for line in view.details:
                st.markdown(f"- {_format_tagged_markdown(line)}")
        if view.show_expander and view.details:
            with st.expander(view.expander_label, expanded=False):
                for line in view.details:
                    st.markdown(f"- {_format_tagged_markdown(line)}")


def render_system_message(content: str) -> None:
    text = format_tool_event_content(content)
    if not text:
        return
    _render_compact_system_view(compact_system_events([content]))


def render_tool_events_live(tool_events: list[str]) -> None:
    cleaned = [event for event in tool_events if str(event).strip()]
    if not cleaned:
        return
    _render_compact_system_view(compact_system_events(cleaned))


def render_kp_story_message(content: str) -> None:
    text = content.strip()
    if not text:
        return
    with st.chat_message("assistant", avatar=_STORY_KP_AVATAR):
        st.caption("KP · 叙事")
        st.markdown(text)


def kp_story_chat_message(*, kp_meta: bool = False):
    """KP 叙事流式输出的 chat 容器（与系统消息分离）。"""
    if kp_meta:
        return st.chat_message("assistant", avatar=_KP_META_AVATAR)
    return st.chat_message("assistant", avatar=_STORY_KP_AVATAR)


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
    index = 0
    while index < len(history):
        msg = history[index]
        if msg.role == "system":
            batch: list[str] = []
            while index < len(history) and history[index].role == "system":
                batch.append(history[index].content)
                index += 1
            _render_compact_system_view(compact_system_events(batch))
            continue
        if msg.role == "user" and is_kp_directive(msg.content):
            _render_kp_meta_user_message(msg.content)
            index += 1
            continue
        if msg.role == "assistant" and is_kp_meta_response(msg.content):
            _render_kp_meta_assistant_message(msg.content)
            index += 1
            continue
        if msg.role == "assistant":
            render_kp_story_message(msg.content)
            index += 1
            continue
        with st.chat_message("user"):
            st.markdown(msg.content)
        index += 1


def render_chat_input(disabled: bool = False, placeholder: str | None = None) -> str | None:
    """固定在页面底部的聊天输入框（须作为页面最后一个 Streamlit 组件调用）。"""
    hint = placeholder or (
        "描述你的行动，例如：检查手机里的匿名邮件……"
        "（规则申诉以 【kp】 开头，如「【kp】刚才任务不应失败」）"
    )
    return st.chat_input(hint, disabled=disabled, key="player_chat_input")
