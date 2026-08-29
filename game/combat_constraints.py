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
_ATTACK_FAILED_MARKERS = ("→ 未命中", "找不到存活的敌人", "无法攻击", "超出射程", "射程不足")
_ATTACK_RESOLUTION_PREFIXES = ("攻击 ", "使用 ", "💔")


def mechanical_events_include_combat_block(events: list[str]) -> bool:
    return any(marker in event for event in events for marker in _ACTION_BLOCKED_MARKERS)


def mechanical_events_include_attack_failure(events: list[str]) -> bool:
    return any(
        "攻击" in event and any(marker in event for marker in _ATTACK_FAILED_MARKERS)
        for event in events
    )


def _attack_resolution_events(events: list[str]) -> list[str]:
    resolved: list[str] = []
    for event in events:
        if any(event.startswith(prefix) for prefix in _ATTACK_RESOLUTION_PREFIXES):
            resolved.append(event)
        elif event.startswith("⚠️") and ("伤害" in event or "攻击" in event):
            resolved.append(event)
    return resolved


def format_damage_constraints_for_kp(mechanical_events: list[str]) -> str:
    """攻击/使用物品造成伤害时，要求 KP 与机械数字一致。"""
    attack_lines = _attack_resolution_events(mechanical_events)
    if not attack_lines:
        return ""

    lines = ["【伤害约束 — 叙事必须与下列机械结果一致】"]
    for event in attack_lines:
        lines.append(f"- {event}")
    lines.extend(
        [
            "- **禁止编造**与上述不同的伤害点数、是否命中、是否击倒；场面描写可文学化，但后果强度须对齐。",
            "- 敌人 **SP 完全阻挡** 时：可写护甲/外壳挡住，**不得**写目标失血、重创、倒地。",
            "- **武器 + 技能同击**（如凡剑+裂气斩）：叙事可写剑与气劲，致命程度以合计伤害为准。",
            "- 玩家受击、治疗、消耗品 `use_damage`/`heal_dice` 亦同：数值以【已发生的结果】为准。",
        ]
    )
    return "\n".join(lines)


def format_combat_constraints_for_kp(
    mechanical_events: list[str],
    route: ActionRouteResult | None,
) -> str:
    blocked = mechanical_events_include_combat_block(mechanical_events)
    attack_failed = mechanical_events_include_attack_failure(mechanical_events)
    damage_constraints = format_damage_constraints_for_kp(mechanical_events)
    if not blocked and not attack_failed and not damage_constraints:
        return ""

    sections: list[str] = []
    if damage_constraints:
        sections.append(damage_constraints)

    if blocked or attack_failed:
        lines = ["【战斗约束 — 本轮叙事必须遵守】"]
        for event in mechanical_events:
            if any(marker in event for marker in _ACTION_BLOCKED_MARKERS + _ATTACK_FAILED_MARKERS):
                lines.append(f"- {event}")
            elif event.startswith(("攻击 ", "💔", "⚠️")):
                lines.append(f"- {event}")

        if blocked:
            lines.append(
                "- 被动作经济驳回的部分**不得**在叙事中写成已成功（例如主要动作已用尽则不可写射击命中）。"
            )
            if route and route.item_usage == "pickup":
                lines.append(
                    "- 若系统已记录「免费物件互动：拾取 xxx」，KP 可写拾取过程；物品入库在叙事后由系统结算。"
                )
                lines.append("- 若未出现拾取动作额度记录，不得写已成功捡起该物品。")
        if attack_failed:
            lines.append("- 攻击未命中、未执行或超出射程时，不得写目标已被该次攻击击倒/重创。")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)
