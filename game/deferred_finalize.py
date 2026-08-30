"""回合后台收尾：记忆整理、地图更新、行动建议（不阻塞 UI）。"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from chain.async_utils import run_async
from game.models import Character, ChatMessage, GameState
from game.scenario import Scenario
from game.turn_context import TurnContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeferredFinalizeResult:
    action_suggestions: list[str] = field(default_factory=list)
    summary_updated: bool = False
    error: str = ""


@dataclass(frozen=True)
class DeferredFinalizeSnapshot:
    turn_count: int
    history: list[ChatMessage]
    kp_response: str
    map_needs_update: bool
    map_travel_from: str


class DeferredFinalizeStore:
    """线程安全：后台任务状态与结果（主线程轮询应用）。"""

    _lock = threading.Lock()
    _running: set[str] = set()
    _results: dict[str, DeferredFinalizeResult] = {}

    @classmethod
    def is_running(cls, save_id: str) -> bool:
        if not save_id:
            return False
        with cls._lock:
            return save_id in cls._running

    @classmethod
    def any_running(cls) -> bool:
        with cls._lock:
            return bool(cls._running)

    @classmethod
    def pop_result(cls, save_id: str) -> DeferredFinalizeResult | None:
        if not save_id:
            return None
        with cls._lock:
            return cls._results.pop(save_id, None)

    @classmethod
    def submit(cls, save_id: str, worker: Callable[[], DeferredFinalizeResult]) -> bool:
        if not save_id:
            return False
        with cls._lock:
            if save_id in cls._running:
                logger.info("跳过后台收尾：存档 %s 已有任务在跑", save_id)
                return False
            cls._running.add(save_id)

        def _run() -> None:
            try:
                result = worker()
            except Exception as exc:
                logger.exception("后台收尾失败")
                result = DeferredFinalizeResult(error=str(exc))
            with cls._lock:
                cls._running.discard(save_id)
                cls._results[save_id] = result

        threading.Thread(target=_run, daemon=True).start()
        return True


def snapshot_from_context(ctx: TurnContext, kp_response: str) -> DeferredFinalizeSnapshot:
    history = list(ctx.history)
    cleaned = kp_response.strip()
    if cleaned:
        history.append(ChatMessage(role="assistant", content=cleaned))
    return DeferredFinalizeSnapshot(
        turn_count=ctx.game_state.turn_count,
        history=history,
        kp_response=cleaned,
        map_needs_update=ctx.map_needs_update,
        map_travel_from=ctx.map_travel_from.strip(),
    )


def schedule_deferred_finalize(
    *,
    save_id: str,
    orchestrator,
    character: Character,
    game_state: GameState,
    scenario: Scenario,
    ctx: TurnContext,
    kp_response: str,
) -> bool:
    """提交后台收尾任务；返回是否成功入队。"""
    snap = snapshot_from_context(ctx, kp_response)

    def worker() -> DeferredFinalizeResult:
        return run_async(
            orchestrator.pipeline.run_deferred_finalize(
                character=character,
                game_state=game_state,
                scenario=scenario,
                ctx=ctx,
                snapshot=snap,
            )
        )

    return DeferredFinalizeStore.submit(save_id, worker)
