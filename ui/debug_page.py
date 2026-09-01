"""Debug 日志页 UI。"""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from config.logging_setup import (
    clear_log_buffer,
    get_log_buffer_snapshot,
    log_file_path,
    tail_log_file,
)
from ui.auth import render_login_gate


def _ensure_auth_state() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False


def _format_buffer_rows(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "（暂无日志，进行几轮游戏后会出现在此）"
    return "\n".join(row["text"] for row in rows)


@st.fragment(run_every=timedelta(seconds=2))
def _live_log_fragment(*, level: str, limit: int) -> None:
    rows = get_log_buffer_snapshot(level=None if level == "ALL" else level, limit=limit)
    st.code(_format_buffer_rows(rows), language="log")


def render_debug_page() -> None:
    _ensure_auth_state()
    if not st.session_state.get("authenticated"):
        render_login_gate()
        return

    st.title("🐛 Debug 日志")
    st.caption(f"日志文件：`{log_file_path()}` · 仅可通过地址栏 `/debug` 访问")

    nav_left, nav_right = st.columns([1, 1])
    with nav_left:
        if st.button("← 返回游戏", use_container_width=True):
            st.switch_page("app.py")
    with nav_right:
        if st.button("清空内存缓冲", use_container_width=True):
            clear_log_buffer()
            st.toast("已清空当前进程的内存日志缓冲")
            st.rerun()

    level = st.selectbox(
        "级别过滤（内存缓冲）",
        options=["ALL", "DEBUG", "INFO", "WARNING", "ERROR"],
        index=1,
    )
    limit = st.slider("显示条数（内存缓冲）", min_value=50, max_value=2000, value=400, step=50)
    auto_refresh = st.toggle("自动刷新内存缓冲", value=True)

    tab_live, tab_file = st.tabs(["当前进程（内存）", "日志文件（tail）"])

    with tab_live:
        st.caption("Streamlit 重启后会清空；完整历史请看「日志文件」。")
        if auto_refresh:
            _live_log_fragment(level=level, limit=limit)
        else:
            rows = get_log_buffer_snapshot(
                level=None if level == "ALL" else level,
                limit=limit,
            )
            st.code(_format_buffer_rows(rows), language="log")
            if st.button("刷新"):
                st.rerun()

    with tab_file:
        file_lines = st.slider("文件 tail 行数", min_value=100, max_value=3000, value=600, step=100)
        st.code(tail_log_file(lines=file_lines), language="log")
