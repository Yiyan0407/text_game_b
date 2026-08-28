"""回合内 Agent 调用路由：决定哪些 LLM 任务需要运行。"""

from __future__ import annotations

from game.turn_context import TurnContext

_ITEM_TOPIC_MARKERS = (
    "义体",
    "植入",
    "改造",
    "装备",
    "穿戴",
    "装配",
    "卸下",
    "背包",
    "物品",
    "芯片",
    "模块",
    "武器",
    "防具",
    "工具",
    "拾取",
    "购买",
    "获得",
    "取出",
    "启用",
    "检查",
    "盘点",
)
_KP_ITEM_MARKERS = (
    "获得",
    "装备",
    "植入",
    "穿戴",
    "装配",
    "义体",
    "芯片",
    "模块",
    "背包",
    "取出",
    "封存",
    "挂载",
    "HUD",
    "接口",
)
_MECHANICAL_ITEM_MARKERS = ("获得：", "装备：", "持用：", "握持：", "背包新增", "支付")


def should_run_item_sync(ctx: TurnContext) -> bool:
    """KP 叙事后是否调用 ItemSyncAgent。"""
    if ctx.rejected:
        return False
    kp = ctx.kp_response.strip()
    if not kp:
        return False

    if any(marker in event for event in ctx.mechanical_events for marker in _MECHANICAL_ITEM_MARKERS):
        return True

    user_text = ctx.effective_input
    if any(marker in user_text for marker in _ITEM_TOPIC_MARKERS):
        return True

    if any(marker in kp for marker in _KP_ITEM_MARKERS):
        return True

    background = ctx.character.background.strip()
    if background and any(marker in background for marker in ("义体", "植入", "改造", "战斗组")):
        if any(marker in user_text for marker in ("义体", "植入", "检查", "模块", "体内")):
            return True
        if any(marker in kp for marker in ("义体", "植入", "模块", "体内")):
            return True

    return False


def should_run_stat_forge(ctx: TurnContext) -> bool:
    """存在尚未经 StatForge 裁定的物品/技能时运行（不依赖关键词）。"""
    if ctx.rejected:
        return False
    from game.stat_forge import collect_forge_targets

    return bool(collect_forge_targets(ctx.character))
