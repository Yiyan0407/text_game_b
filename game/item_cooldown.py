"""可重复使用物品与后台冷却进程。"""

from __future__ import annotations

import re

from game.inventory import InventoryItem
from game.models import GameState

_REUSABLE_NAME_MARKERS = (
    "记忆消除",
    "记忆抹除",
    "病毒分析仪",
    "便携式病毒分析",
    "量子加密通讯",
    "通讯器",
    "通讯模块",
    "光学迷彩",
)

_COOLDOWN_LABEL_RE = re.compile(r"冷却|充能|reload|recharge", re.IGNORECASE)


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().casefold())


def item_matches_background_process(item_name: str, process_label: str) -> bool:
    item_key = _normalize_key(item_name)
    label_key = _normalize_key(process_label)
    if not item_key or not label_key:
        return False
    return item_key in label_key or label_key.startswith(item_key)


def item_cooldown_remaining_minutes(game_state: GameState, item_name: str) -> int | None:
    """若物品处于后台冷却中，返回剩余分钟数。"""
    for process in game_state.background_processes:
        if process.status != "running":
            continue
        if not item_matches_background_process(item_name, process.label):
            continue
        if not _COOLDOWN_LABEL_RE.search(process.label):
            continue
        due_at = process.started_at_minutes + process.duration_minutes
        remaining = due_at - game_state.elapsed_minutes
        if remaining > 0:
            return remaining
    return None


def retains_inventory_on_use(item: InventoryItem) -> bool:
    """使用后仍保留在背包（冷却后可再用），而非一次性消耗。"""
    if item.kind == "document":
        return True
    if item.kind == "durable":
        return True

    effects = item.effects
    if effects and effects.forged:
        if effects.consumes_on_use is False:
            return True
        if effects.consumes_on_use is True:
            return False
        if effects.use_tag and not effects.heal_dice and not effects.use_damage:
            return True

    name = item.name.strip()
    return any(marker in name for marker in _REUSABLE_NAME_MARKERS)
