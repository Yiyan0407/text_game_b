"""Streamlit 层：后台回合收尾调度与结果应用。"""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from chain.async_utils import run_async
from config.settings import get_settings
from game.deferred_finalize import (
    DeferredFinalizeResult,
    DeferredFinalizeStore,
    schedule_deferred_finalize,
    snapshot_from_context,
)
from game.session import persist_save
from game.turn_context import TurnContext


def resolve_save_key() -> str:
    save_id = st.session_state.get("current_save_id")
    if save_id:
        return str(save_id)
    game_state = st.session_state.get("game_state")
    character = st.session_state.get("character")
    if game_state is not None and character is not None:
        scenario_id = getattr(game_state, "scenario_id", "") or "unknown"
        return f"draft:{scenario_id}:{character.name}"
    return "draft:anonymous"


def apply_deferred_result(result: DeferredFinalizeResult) -> None:
    if result.action_suggestions:
        st.session_state.action_suggestions = result.action_suggestions
    if result.error:
        st.session_state.deferred_finalize_error = result.error
    else:
        st.session_state.pop("deferred_finalize_error", None)
        persist_save()


def poll_deferred_results() -> bool:
    """主线程取回后台结果。返回是否应用了新结果。"""
    result = DeferredFinalizeStore.pop_result(resolve_save_key())
    if result is None:
        return False
    apply_deferred_result(result)
    return True


def schedule_turn_finalize(
    *,
    orchestrator,
    ctx: TurnContext | None,
    kp_response: str,
) -> None:
    """KP 叙事与物品同步完成后调用：后台跑记忆/地图/建议。"""
    if ctx is None or not kp_response.strip():
        return

    character = ctx.character
    game_state = ctx.game_state
    scenario = ctx.scenario
    save_key = resolve_save_key()
    snap = snapshot_from_context(ctx, kp_response)

    if not get_settings().enable_deferred_finalize:
        result = run_async(
            orchestrator.pipeline.run_deferred_finalize(
                character=character,
                game_state=game_state,
                scenario=scenario,
                ctx=ctx,
                snapshot=snap,
            )
        )
        apply_deferred_result(result)
        return

    schedule_deferred_finalize(
        save_id=save_key,
        orchestrator=orchestrator,
        character=character,
        game_state=game_state,
        scenario=scenario,
        ctx=ctx,
        kp_response=kp_response,
    )


def render_deferred_status() -> None:
    if DeferredFinalizeStore.is_running(resolve_save_key()):
        st.caption("🧠 后台整理记忆、地图与行动建议中…")
    error = st.session_state.get("deferred_finalize_error")
    if error:
        st.caption(f"⚠️ 后台整理未完成：{error}")


@st.fragment(run_every=timedelta(seconds=2))
def deferred_poll_fragment() -> None:
    """后台任务进行中时轮询，完成后刷新建议与存档。"""
    if not DeferredFinalizeStore.any_running():
        return
    if poll_deferred_results():
        st.rerun()


def finalize_streaming_turn_with_deferred(
    orchestrator,
    turn_context: TurnContext | None,
    full_response: str,
    *,
    run_item_sync_phase,
    finish_turn,
    kp_meta: bool = False,
) -> "TurnResult":
    from ui.streaming import finalize_streaming_turn

    def _schedule(kp_response: str) -> None:
        schedule_turn_finalize(
            orchestrator=orchestrator,
            ctx=turn_context,
            kp_response=kp_response,
        )

    return finalize_streaming_turn(
        full_response,
        run_item_sync_phase=run_item_sync_phase,
        finish_turn=finish_turn,
        turn_context=turn_context,
        schedule_finalize=_schedule if turn_context is not None and not kp_meta else None,
        kp_meta=kp_meta,
    )
