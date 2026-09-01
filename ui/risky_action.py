"""高风险操作（如永久删除）的二次确认。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

SESSION_KEY = "risky_action_pending"
CONFIRMED_FLAG = "risky_action_confirmed"
CONFIRM_BUTTON_KEY = "risky_action_confirm"
CANCEL_BUTTON_KEY = "risky_action_cancel"

ACTION_DELETE_SAVE = "delete_save"
ACTION_DELETE_SCENARIO = "delete_scenario"

PENDING = object()


def _has_dialog() -> bool:
    return hasattr(st, "dialog")


def render_delete_confirm_dialog(
    *,
    message: str,
    on_confirm: Callable[[], None],
    on_cancel: Callable[[], None] | None = None,
    title: str = "确认删除",
    confirm_label: str = "确认删除",
    cancel_label: str = "取消",
    dialog_key: str = "delete",
) -> None:
    """渲染删除确认弹窗；无 st.dialog 时回退为页内 warning。"""

    def _cancel() -> None:
        if on_cancel is not None:
            on_cancel()
        else:
            st.rerun()

    if _has_dialog():

        @st.dialog(title, width="small")
        def _body() -> None:
            st.markdown(message)
            c1, c2 = st.columns(2)
            if c1.button(
                confirm_label,
                type="primary",
                use_container_width=True,
                key=f"{dialog_key}_confirm",
            ):
                on_confirm()
            if c2.button(
                cancel_label,
                use_container_width=True,
                key=f"{dialog_key}_cancel",
            ):
                _cancel()

        _body()
        return

    st.warning(message)
    c1, c2 = st.columns(2)
    if c1.button(
        confirm_label,
        type="primary",
        use_container_width=True,
        key=f"{dialog_key}_confirm_inline",
    ):
        on_confirm()
    if c2.button(cancel_label, use_container_width=True, key=f"{dialog_key}_cancel_inline"):
        _cancel()


def queue_risky_action(
    action: str,
    *,
    message: str,
    context: dict[str, Any] | None = None,
) -> None:
    st.session_state[SESSION_KEY] = {
        "action": action,
        "message": message,
        "context": context or {},
    }
    st.rerun()


def queue_delete_save(save_id: str, *, label: str) -> None:
    queue_risky_action(
        ACTION_DELETE_SAVE,
        message=f"确定删除存档「{label}」？此操作无法恢复。",
        context={"save_id": save_id, "label": label},
    )


def queue_delete_scenario(scenario_id: str, *, title: str) -> None:
    queue_risky_action(
        ACTION_DELETE_SCENARIO,
        message=(
            f"确定删除剧本「{title}」？"
            "此操作无法恢复；已有存档不会自动删除，但可能无法再正常加载该模组。"
        ),
        context={"scenario_id": scenario_id, "title": title},
    )


def get_risky_action() -> dict[str, Any] | None:
    pending = st.session_state.get(SESSION_KEY)
    if pending is None:
        legacy = st.session_state.get(CONFIRM_BUTTON_KEY)
        if isinstance(legacy, dict) and "action" in legacy:
            st.session_state[SESSION_KEY] = legacy
            st.session_state.pop(CONFIRM_BUTTON_KEY, None)
            pending = legacy
    return pending if isinstance(pending, dict) else None


def clear_risky_action() -> None:
    st.session_state.pop(SESSION_KEY, None)
    st.session_state.pop(CONFIRMED_FLAG, None)


def handle_risky_action_prompt(
    *,
    confirm_label: str = "确认删除",
    cancel_label: str = "取消",
) -> dict[str, Any] | Any | None:
    """有待确认操作时弹出对话框。返回已确认的操作 dict、PENDING，或 None。"""
    pending = get_risky_action()
    if not pending:
        return None

    if st.session_state.pop(CONFIRMED_FLAG, False):
        result = pending
        clear_risky_action()
        return result

    def _confirm() -> None:
        st.session_state[CONFIRMED_FLAG] = True
        st.rerun()

    def _cancel() -> None:
        clear_risky_action()
        st.rerun()

    render_delete_confirm_dialog(
        message=pending["message"],
        on_confirm=_confirm,
        on_cancel=_cancel,
        confirm_label=confirm_label,
        cancel_label=cancel_label,
        dialog_key="risky_action",
    )
    return PENDING
