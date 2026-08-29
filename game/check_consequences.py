"""属性检定失败后的机械后果。"""

from __future__ import annotations

import re

from config.settings import get_settings
from game.effect_resolver import apply_incoming_damage
from game.models import ABILITY_LABELS, Character, GameState, NPCRelation
from game.results import AbilityCheckResult, ActionRouteResult

_DANGEROUS_MARKERS = (
    "攀爬",
    "跳跃",
    "翻越",
    "拆除",
    "陷阱",
    "闪避",
    "挣脱",
    "潜泳",
    "高空",
    "危房",
    "爆炸",
    "硬闯",
    "强突",
)
_SOCIAL_MARKERS = (
    "说服",
    "交涉",
    "欺骗",
    "哄",
    "谈判",
    "请求",
    "质问",
    "套话",
    "劝",
    "求",
    "辩",
)
_STEALTH_MARKERS = (
    "潜行",
    "潜入",
    "隐蔽",
    "悄悄",
    "躲开",
    "避开",
    "侦察",
    "尾随",
    "渗透",
    "撬锁",
    "开锁",
    "黑入",
    "偷听",
    "窥探",
    "偷",
    "偷窃",
)


def _action_text(route: ActionRouteResult) -> str:
    return " ".join(
        part
        for part in (route.action_intent, route.scope_stop)
        if part and part.strip()
    )


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def is_dangerous_attempt(route: ActionRouteResult) -> bool:
    text = _action_text(route)
    if _contains_any(text, _DANGEROUS_MARKERS):
        return True
    return route.trigger_combat or route.mode == "combat"


def is_social_attempt(route: ActionRouteResult) -> bool:
    text = _action_text(route)
    return _contains_any(text, _SOCIAL_MARKERS)


def is_stealth_attempt(route: ActionRouteResult) -> bool:
    text = _action_text(route)
    return _contains_any(text, _STEALTH_MARKERS)


def _find_target_npc(game_state: GameState, route: ActionRouteResult) -> NPCRelation | None:
    text = _action_text(route)
    for npc in game_state.npcs:
        name = npc.name.strip()
        if not name:
            continue
        if name in text:
            return npc
        core = re.sub(r"[（(].+[)）]", "", name).strip()
        if core and core in text:
            return npc
    return game_state.npcs[-1] if len(game_state.npcs) == 1 else None


def _worsen_attitude(attitude: str) -> str | None:
    if attitude == "friendly":
        return "neutral"
    if attitude == "neutral":
        return "hostile"
    if attitude == "unknown":
        return "neutral"
    return None


def _apply_failure_damage(character: Character, raw_damage: int) -> list[str]:
    """检定失败伤害须走 SP 机制（与战斗一致）。"""
    if raw_damage <= 0:
        return []

    result = apply_incoming_damage(character, raw_damage)
    if character.hp < 1:
        character.hp = 1

    if result.fully_blocked and result.effective_sp > 0:
        source = f"（{result.sp_source}）" if result.sp_source else ""
        return [
            f"🛡️ 失败反制：SP{result.effective_sp} 完全挡住 {raw_damage} 点伤害{source}"
        ]

    return result.format_events()


def apply_check_failure_consequences(
    route: ActionRouteResult,
    result: AbilityCheckResult,
    character: Character,
    game_state: GameState,
) -> list[str]:
    if result.success:
        return []

    events: list[str] = []
    settings = get_settings()
    margin = max(0, result.dc - result.check_total)
    intent = route.action_intent.strip() or "本次行动"
    ability_label = ABILITY_LABELS.get(result.ability, result.ability.upper())

    fact = (
        f"尝试「{intent}」失败（{ability_label}检定 {result.check_total} vs DC {result.dc}）"
    )
    game_state.add_memory_facts([fact], settings.max_memory_facts)
    events.append(f"📌 行动失败：{intent}")

    if is_dangerous_attempt(route) or (margin >= 8 and result.ability in ("str", "dex", "con")):
        raw_damage = min(8, max(1, margin // 2))
        events.extend(_apply_failure_damage(character, raw_damage))

    if result.ability in ("cha", "wis") and is_social_attempt(route):
        npc = _find_target_npc(game_state, route)
        if npc is not None:
            new_attitude = _worsen_attitude(npc.attitude)
            if new_attitude and new_attitude != npc.attitude:
                old = npc.attitude
                npc.attitude = new_attitude
                events.append(f"😠 {npc.name} 态度恶化：{old} → {new_attitude}")
        else:
            alert = f"社交尝试「{intent}」失败，对方态度可能转差"
            game_state.add_memory_facts([alert], settings.max_memory_facts)
            events.append("⚠️ 社交失败：关系可能恶化")

    if is_stealth_attempt(route) or (
        result.ability == "dex" and route.skill_usage == "use"
    ):
        alert = "潜入/潜行尝试失败，现场警戒可能已提高"
        game_state.add_memory_facts([alert], settings.max_memory_facts)
        events.append("⚠️ 潜行失败：对方可能已察觉")

    if route.skill_usage == "learn":
        learn_fact = f"向他人学习「{', '.join(route.referenced_skills) or '新技能'}」失败"
        game_state.add_memory_facts([learn_fact], settings.max_memory_facts)
        events.append("📚 学习失败：未掌握新技能")

    return events


def mechanical_events_include_check_failure(events: list[str]) -> bool:
    for event in events:
        if "检定" in event and "失败" in event:
            return True
    return False


def format_check_failure_constraints_for_kp(
    mechanical_events: list[str],
    route: ActionRouteResult | None,
) -> str:
    if not mechanical_events_include_check_failure(mechanical_events):
        return ""

    lines = ["【检定失败 — 本轮叙事必须遵守】"]
    for event in mechanical_events:
        if "检定" in event and "失败" in event:
            lines.append(f"- 机械结果：{event}")
        elif event.startswith(("💔", "😠", "⚠️", "📌", "📚", "🛡️", "💥")):
            lines.append(f"- {event}")
    lines.extend(
        [
            "- 本轮不得写行动成功、不得获得本应失败才能到手的物品/情报/技能。",
            "- 须写明确失败后果：失手、暴露、受伤、关系恶化、时间耽搁等，至少体现一项。",
            "- 可推进剧情，但方向必须是 setback，不是原计划的收益。",
        ]
    )
    if route and route.scope_stop.strip():
        lines.append(f"- 叙事仍应收笔于：{route.scope_stop.strip()}")
    return "\n".join(lines)
