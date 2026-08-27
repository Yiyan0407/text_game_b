import hashlib

import streamlit as st

from game.models import Character, ChatMessage, GameState
from game.pdf_export import build_game_pdf, suggest_pdf_filename
from game.scenario import Scenario


def _messages_fingerprint(messages: list[ChatMessage], game_state: GameState) -> str:
    payload = "\n".join(f"{msg.role}:{msg.content}" for msg in messages)
    payload += f"\nturn:{game_state.turn_count}\nsummary:{game_state.story_summary}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_game_pdf_download(
    scenario: Scenario,
    character: Character,
    game_state: GameState,
    messages: list[ChatMessage],
) -> None:
    if not messages:
        st.download_button(
            "📄 下载游戏记录 PDF",
            data=b"",
            file_name="game.pdf",
            mime="application/pdf",
            use_container_width=True,
            disabled=True,
            help="开始游戏后可导出完整对话与进度。",
        )
        return

    fingerprint = _messages_fingerprint(messages, game_state)
    cache_key = "_export_pdf_cache"
    cached = st.session_state.get(cache_key)
    if not cached or cached.get("fingerprint") != fingerprint:
        try:
            pdf_bytes = build_game_pdf(
                scenario=scenario,
                character=character,
                game_state=game_state,
                messages=messages,
            )
        except Exception as exc:
            st.session_state[cache_key] = {"fingerprint": fingerprint, "error": str(exc)}
        else:
            st.session_state[cache_key] = {
                "fingerprint": fingerprint,
                "bytes": pdf_bytes,
                "filename": suggest_pdf_filename(scenario, character),
            }

    cached = st.session_state.get(cache_key, {})
    if cached.get("error"):
        st.caption(f"PDF 生成失败：{cached['error']}")
        return

    pdf_bytes = cached.get("bytes", b"")
    filename = cached.get("filename", "game.pdf")
    st.download_button(
        "📄 下载游戏记录 PDF",
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf",
        use_container_width=True,
        help="导出角色、任务、摘要与完整聊天记录，便于分享。",
    )
