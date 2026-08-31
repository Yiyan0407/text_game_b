"""回合内 Agent 调用路由：Settlement 计划与确定性触发。"""

from __future__ import annotations

from game.models import GameState
from game.post_kp_mechanics import resolve_post_kp_mechanics
from game.results import ActionRouteResult
from game.settlement_plan import (
    OPENING_SETTLEMENT_PLAN,
    SettlementPlan,
    SettlementRouterError,
    format_settlement_plan_event,
)
from game.turn_context import TurnContext

__all__ = [
    "SettlementPlan",
    "SettlementRouterError",
    "OPENING_SETTLEMENT_PLAN",
    "needs_post_kp_mechanical",
    "run_post_kp_mechanical_if_needed",
    "parse_settlement_plan",
    "resolve_settlement_plan",
    "should_run_stat_forge",
    "format_settlement_plan_event",
]

from game.settlement_plan import parse_settlement_plan  # noqa: E402


def needs_post_kp_mechanical(
    route: ActionRouteResult | None,
    game_state: GameState,
) -> bool:
    """购买/用物/战斗拾取用物 — 代码触发，不经 Settlement Router。"""
    if route is None or not route.approved:
        return False
    if game_state.is_in_combat():
        return route.item_usage in ("pickup", "use")
    return route.item_usage in ("purchase", "use", "pickup")


def run_post_kp_mechanical_if_needed(
    route: ActionRouteResult | None,
    character,
    game_state: GameState,
    pre_kp_events: list[str],
) -> list[str]:
    if not needs_post_kp_mechanical(route, game_state):
        return []
    assert route is not None
    return resolve_post_kp_mechanics(route, character, game_state, pre_kp_events)


def resolve_settlement_plan(
    ctx: TurnContext,
    *,
    router_plan: SettlementPlan | None = None,
) -> SettlementPlan:
    if ctx.rejected or not ctx.kp_response.strip():
        return SettlementPlan(
            inventory_sync=False,
            skill_sync=False,
            time_sync=False,
            world_sync=False,
            reason="rejected or no kp response",
        )
    if ctx.is_opening:
        return OPENING_SETTLEMENT_PLAN
    if router_plan is not None:
        return router_plan
    raise SettlementRouterError("非 opening 回合缺少 Settlement Router plan")


def should_run_stat_forge(ctx: TurnContext) -> bool:
    """存在尚未经 StatForge 裁定的物品/技能时运行（不依赖关键词）。"""
    if ctx.rejected:
        return False
    from game.stat_forge import collect_forge_targets

    return bool(collect_forge_targets(ctx.character))
