"""KP 后结算计划模型与解析。"""

from __future__ import annotations

from dataclasses import dataclass

from game.results import ActionRouteResult


class SettlementRouterError(ValueError):
    """Settlement Router 输出无法解析为有效 plan。"""


@dataclass(frozen=True)
class SettlementPlan:
    inventory_sync: bool
    skill_sync: bool
    time_sync: bool
    world_sync: bool
    reason: str = ""


def ensure_skill_sync_for_acquisition(
    route: ActionRouteResult | None,
    plan: SettlementPlan,
) -> SettlementPlan:
    """学习类行动强制开启 skill_sync，避免 Settlement Router 漏开。"""
    if route is None or plan.skill_sync:
        return plan
    if route.skill_usage not in ("learn",):
        return plan
    reason = plan.reason.strip()
    suffix = "强制 skill_sync（技能获取）"
    merged = f"{reason}；{suffix}" if reason else suffix
    return SettlementPlan(
        inventory_sync=plan.inventory_sync,
        skill_sync=True,
        time_sync=plan.time_sync,
        world_sync=plan.world_sync,
        reason=merged,
    )


OPENING_SETTLEMENT_PLAN = SettlementPlan(
    inventory_sync=True,
    skill_sync=False,
    time_sync=True,
    world_sync=True,
    reason="opening default",
)


def parse_settlement_plan(data: dict) -> SettlementPlan:
    tasks = data.get("tasks")
    if not isinstance(tasks, dict):
        raise SettlementRouterError(f"结算路由 JSON 缺少 tasks 对象: {data!r}")
    try:
        return SettlementPlan(
            inventory_sync=bool(tasks.get("inventory_sync", False)),
            skill_sync=bool(tasks.get("skill_sync", False)),
            time_sync=bool(tasks.get("time_sync", True)),
            world_sync=bool(tasks.get("world_sync", False)),
            reason=str(data.get("reason", "")).strip(),
        )
    except (TypeError, ValueError) as exc:
        raise SettlementRouterError(f"结算路由 JSON 字段异常: {data!r}") from exc


def format_settlement_plan_event(plan: SettlementPlan) -> str:
    flags = []
    if plan.inventory_sync:
        flags.append("inventory")
    if plan.skill_sync:
        flags.append("skill")
    if plan.time_sync:
        flags.append("time")
    if plan.world_sync:
        flags.append("world")
    tasks = ",".join(flags) if flags else "none"
    reason = plan.reason.strip() or "—"
    return f"结算路由：{tasks}（{reason}）"
