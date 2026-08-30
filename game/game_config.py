"""每局游戏的可调选项（KP 引导、背景审核等）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from game.models import GameState, ScenarioProgress
from game.scenario import Scenario

KpGuidance = Literal["freeform", "balanced", "script_guided"]

KP_GUIDANCE_LABELS: dict[KpGuidance, str] = {
    "freeform": "自由即兴 — 玩家主导，模组节点仅作背景",
    "balanced": "平衡引导 — KP 侧追踪进度，周期轻推（默认）",
    "script_guided": "按剧本推进 — 追踪 beats，逾期须引入节点要素",
}


class GameConfig(BaseModel):
    kp_guidance: KpGuidance = "balanced"
    enable_background_validation: bool = True


def default_game_config() -> GameConfig:
    return GameConfig()


def _append_hint(user_input: str, hint: str) -> str:
    if hint in user_input:
        return user_input
    return f"{user_input}\n\n{hint}"


def apply_guidance_hint(
    user_input: str,
    turn_count: int,
    config: GameConfig,
    *,
    scenario: Scenario | None = None,
    progress: ScenarioProgress | None = None,
) -> str:
    """按游戏配置决定是否追加 KP 引导提示。"""
    text = user_input.strip()
    if not text:
        return user_input

    confused_markers = ("怎么办", "接下来", "不知道", "该怎么", "做什么", "help", "?")
    confused = any(marker in text.lower() for marker in confused_markers)
    short_input = len(text) <= 4

    hints: list[str] = []

    if config.kp_guidance == "freeform":
        if confused:
            hints.append(
                "[KP 引导：玩家可能需要方向。请用叙事方式给出 1–2 个与当前情境相关的方向，"
                "不要主动推进模组关键节点，不要出戏，不要列编号选项。]"
            )
    elif config.kp_guidance == "script_guided":
        if scenario and progress and scenario.key_nodes:
            from game.scenario_progress import is_node_overdue, pending_beats

            pending = pending_beats(scenario, progress)
            if pending:
                overdue = is_node_overdue(
                    progress,
                    config.kp_guidance,
                    turn_count=turn_count,
                    has_pending=True,
                )
                if overdue:
                    hints.append(
                        "[KP 引导：按【剧本进度】本回合须引入至少 1 条待完成要素"
                        "（环境事件/通讯/NPC 接触，勿替玩家决策）。]"
                    )
                else:
                    hints.append(
                        "[KP 引导：按【剧本进度】引入待完成要素；"
                        "可让 NPC/环境主动接戏，勿一次性剧透后续节点。]"
                    )
        needs_guidance = turn_count <= 8 or short_input or confused
        if needs_guidance and not hints:
            hints.append(
                "[KP 引导：按模组 key_nodes 推进。请用叙事方式给出 2–3 个与当前或下一关键节点"
                "相关的具体方向（调查、交谈、移动等），可让 NPC/环境主动提供线索，"
                "不要一次性剧透后续节点，不要出戏，不要列编号选项。]"
            )
    else:
        if scenario and progress and scenario.key_nodes:
            from game.scenario_progress import is_node_overdue, pending_beats

            pending = pending_beats(scenario, progress)
            if pending and (
                progress.turns_on_active_node > 0
                and progress.turns_on_active_node % 8 == 0
            ):
                overdue = is_node_overdue(
                    progress,
                    config.kp_guidance,
                    turn_count=turn_count,
                    has_pending=True,
                )
                if overdue:
                    hints.append(
                        "[KP 引导：剧本进展偏慢，可用 1–2 句环境细节铺垫"
                        "【剧本进度】中的待完成要素，勿抢戏。]"
                    )
        needs_guidance = turn_count <= 3 or short_input or confused
        if needs_guidance:
            hints.append(
                "[KP 引导：玩家可能需要方向。请用叙事方式给出 2–3 个具体可尝试的行动方向，"
                "可让 NPC/环境主动接话，不要出戏，不要列编号选项。]"
            )

    result = user_input
    for hint in hints:
        result = _append_hint(result, hint)
    return result
