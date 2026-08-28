"""每局游戏的可调选项（KP 引导、背景审核等）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

KpGuidance = Literal["freeform", "balanced", "script_guided"]

KP_GUIDANCE_LABELS: dict[KpGuidance, str] = {
    "freeform": "自由即兴 — 玩家主导，模组节点仅作背景",
    "balanced": "平衡引导 — 开局与迷茫时轻量提示（默认）",
    "script_guided": "按剧本推进 — 优先铺设关键节点与事件",
}


class GameConfig(BaseModel):
    kp_guidance: KpGuidance = "balanced"
    enable_background_validation: bool = True


def default_game_config() -> GameConfig:
    return GameConfig()


def apply_guidance_hint(user_input: str, turn_count: int, config: GameConfig) -> str:
    """按游戏配置决定是否追加 KP 引导提示。"""
    text = user_input.strip()
    if not text:
        return user_input

    confused_markers = ("怎么办", "接下来", "不知道", "该怎么", "做什么", "help", "?")
    confused = any(marker in text.lower() for marker in confused_markers)
    short_input = len(text) <= 4

    if config.kp_guidance == "freeform":
        if not confused:
            return user_input
        return (
            f"{user_input}\n\n"
            "[KP 引导：玩家可能需要方向。请用叙事方式给出 1–2 个与当前情境相关的方向，"
            "不要主动推进模组关键节点，不要出戏，不要列编号选项。]"
        )

    if config.kp_guidance == "script_guided":
        needs_guidance = turn_count <= 8 or short_input or confused
        if not needs_guidance:
            return user_input
        return (
            f"{user_input}\n\n"
            "[KP 引导：按模组 key_nodes 推进。请用叙事方式给出 2–3 个与当前或下一关键节点"
            "相关的具体方向（调查、交谈、移动等），可让 NPC/环境主动提供线索，"
            "不要一次性剧透后续节点，不要出戏，不要列编号选项。]"
        )

    # balanced — 与原有行为一致
    needs_guidance = turn_count <= 3 or short_input or confused
    if not needs_guidance:
        return user_input
    return (
        f"{user_input}\n\n"
        "[KP 引导：玩家可能需要方向。请用叙事方式给出 2–3 个具体可尝试的行动方向，"
        "可让 NPC/环境主动接话，不要出戏，不要列编号选项。]"
    )
