"""高风险操作（如永久删除）的二次确认。"""

from __future__ import annotations

from typing import Any

import streamlit as st

SESSION_KEY = "risky_action_pending"
CONFIRM_BUTTON_KEY = "risky_action_confirm"
CANCEL_BUTTON_KEY = "risky_action_cancel"

ACTION_DELETE_SAVE = "delete_save"
ACTION_DELETE_SCENARIO = "delete_scenario"

PENDING = object()


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


def handle_risky_action_prompt(
    *,
    confirm_label: str = "确认删除",
    cancel_label: str = "取消",
) -> dict[str, Any] | Any | None:
    """渲染待确认提示。返回已确认的操作 dict、PENDING，或 None。"""
    pending = get_risky_action()
    if not pending:
        return None

    st.warning(pending["message"])
    c1, c2 = st.columns(2)
    if c1.button(
        confirm_label,
        type="primary",
        use_container_width=True,
        key=CONFIRM_BUTTON_KEY,
    ):
        clear_risky_action()
        return pending
    if c2.button(cancel_label, use_container_width=True, key=CANCEL_BUTTON_KEY):
        clear_risky_action()
        st.rerun()
    return PENDING
