"""回合内 Agent 调用路由：决定哪些 LLM 任务需要运行。"""

from __future__ import annotations

from game.turn_context import TurnContext


def should_run_item_sync(ctx: TurnContext) -> bool:
    """KP 叙事后是否调用 ItemSyncAgent。

    默认运行，由 Action Router 的 sync_inventory=false 显式跳过
    （纯对话/移动/观察且本轮不应改变背包或装备时）。
    """
    if ctx.rejected:
        return False
    if not ctx.kp_response.strip():
        return False

    route = ctx.route
    if route is not None and not route.sync_inventory:
        return False

    return True


def should_run_stat_forge(ctx: TurnContext) -> bool:
    """存在尚未经 StatForge 裁定的物品/技能时运行（不依赖关键词）。"""
    if ctx.rejected:
        return False
    from game.stat_forge import collect_forge_targets

    return bool(collect_forge_targets(ctx.character))
