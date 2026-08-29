"""战斗机械结果对 KP 的硬约束。"""

from __future__ import annotations

from game.results import ActionRouteResult

_ACTION_BLOCKED_MARKERS = (
    "本回合主要动作已用尽",
    "本回合附加动作已用尽",
    "还没轮到你",
    "当前无法结束回合",
    "动作资源不足",
)
_ATTACK_FAILED_MARKERS = ("→ 未命中", "找不到存活的敌人")


def mechanical_events_include_combat_block(events: list[str]) -> bool:
    return any(marker in event for event in events for marker in _ACTION_BLOCKED_MARKERS)


def mechanical_events_include_attack_failure(events: list[str]) -> bool:
    return any(
        "攻击" in event and any(marker in event for marker in _ATTACK_FAILED_MARKERS)
        for event in events
    )


def format_combat_constraints_for_kp(
    mechanical_events: list[str],
    route: ActionRouteResult | None,
) -> str:
    blocked = mechanical_events_include_combat_block(mechanical_events)
    attack_failed = mechanical_events_include_attack_failure(mechanical_events)
    if not blocked and not attack_failed:
        return ""

    lines = ["【战斗约束 — 本轮叙事必须遵守】"]
    for event in mechanical_events:
        if any(marker in event for marker in _ACTION_BLOCKED_MARKERS + _ATTACK_FAILED_MARKERS):
            lines.append(f"- {event}")
        elif event.startswith(("攻击 ", "💔", "⚠️")):
            lines.append(f"- {event}")

    if blocked:
        lines.append("- 被动作经济驳回的部分**不得**在叙事中写成已成功（例如主要动作已用尽则不可写射击命中）。")
        if route and route.item_usage == "pickup":
            lines.append("- 若系统已记录「免费物件互动：拾取 xxx」，KP 可写拾取过程；物品入库在叙事后由系统结算。")
            lines.append("- 若未出现拾取动作额度记录，不得写已成功捡起该物品。")
    if attack_failed:
        lines.append("- 攻击未命中或未执行时，不得写目标已被该次攻击击倒/重创。")
    return "\n".join(lines)
