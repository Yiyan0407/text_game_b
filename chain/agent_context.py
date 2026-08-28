"""Agent 共享上下文格式化。"""

from __future__ import annotations

from game.models import Character, ChatMessage, GameState
from game.results import ActionRouteResult


def format_tool_event_line(content: str) -> str:
    text = str(content).strip()
    if text.startswith("🎲 "):
        return text[2:].strip()
    return text


def format_recent_history(history: list[ChatMessage], limit: int = 6) -> str:
    if not history:
        return "（无）"
    recent = history[-limit:]
    lines = []
    for msg in recent:
        if msg.role == "system":
            continue
        role = {"user": "玩家", "assistant": "KP", "system": "系统"}.get(msg.role, msg.role)
        lines.append(f"[{role}] {msg.content}")
    return "\n".join(lines) if lines else "（无）"


def format_recent_system_events(history: list[ChatMessage], limit: int = 15) -> str:
    """提取最近机械/系统结算，供 KP meta 申诉裁定。"""
    if not history:
        return "（无）"
    events: list[str] = []
    for msg in history:
        if msg.role != "system":
            continue
        text = format_tool_event_line(msg.content)
        if text:
            events.append(text)
    recent = events[-limit:]
    if not recent:
        return "（无）"
    return "\n".join(f"- {line}" for line in recent)


def format_mechanical_events(events: list[str]) -> str:
    if not events:
        return "（无）"
    return "\n".join(f"- {event}" for event in events)


def format_route_summary(route: ActionRouteResult | None) -> str:
    if route is None:
        return "（无路由，开场模式）"
    lines = [
        f"行动意图：{route.action_intent}",
        f"叙事边界：{route.scope_stop}",
        f"模式：{route.mode}",
        f"物品用途：{route.item_usage}",
        f"技能用途：{route.skill_usage}",
        f"物品同步：{'是' if route.sync_inventory else '否（跳过 ItemSync）'}",
    ]
    if route.referenced_items:
        lines.append(f"涉及物品：{', '.join(route.referenced_items)}")
    if route.referenced_skills:
        lines.append(f"涉及技能：{', '.join(route.referenced_skills)}")
    if route.skill_usage == "learn":
        lines.append("（学习技能：仅检定成功或 NPC 同意时可 add）")
    return "\n".join(lines)


def format_character_block(character: Character) -> dict[str, str]:
    return {
        "character_name": character.name,
        "character_background": character.background.strip() or "（未填写）",
        "character_abilities": character.format_abilities(),
        "character_inventory": character.format_inventory(),
        "character_equipment": character.format_equipment(),
        "character_skills": character.format_skills(),
    }
