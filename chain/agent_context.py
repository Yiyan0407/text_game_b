"""Agent 共享上下文格式化。"""

from __future__ import annotations

from game.kp_directive import is_kp_meta_response
from game.models import Character, ChatMessage, GameState
from game.results import ActionRouteResult


def format_kp_continuity_hint(history: list[ChatMessage]) -> str:
    """供叙事简报：要求 KP 从上一轮结尾接续，禁止复制粘贴。"""
    last_kp = ""
    for msg in reversed(history):
        if msg.role != "assistant":
            continue
        if is_kp_meta_response(msg.content):
            continue
        last_kp = msg.content.strip()
        break
    if not last_kp:
        return ""

    tail = last_kp.split("\n\n")[-1].strip()
    if len(tail) > 320:
        tail = "…" + tail[-300:].lstrip()
    return (
        "【叙事接续 — 禁止复述】\n"
        f"上一轮 KP 叙事停在：{tail}\n"
        "本回合须从该状态继续：让环境、NPC 或敌对势力产生**新的行动或变化**，"
        "不可复制【历史对话】已有段落，也不可把同一悬念原样再写一遍。"
    )


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
        f"模式：{route.mode}",
        f"物品用途：{route.item_usage}",
        f"技能用途：{route.skill_usage}",
    ]
    if route.referenced_items:
        lines.append(f"涉及物品：{', '.join(route.referenced_items)}")
    if route.referenced_skills:
        lines.append(f"涉及技能：{', '.join(route.referenced_skills)}")
    if route.skill_usage == "learn":
        lines.append("（学习主动技能：仅检定成功或 NPC 同意时可 add，kind=active）")
    return "\n".join(lines)


def format_character_block(character: Character) -> dict[str, str]:
    cap = character.effective_max_hp()
    return {
        "character_name": character.name,
        "character_background": character.background.strip() or "（未填写）",
        "character_abilities": character.format_abilities(),
        "character_inventory": character.format_inventory(),
        "character_equipment": character.format_equipment(),
        "character_skills": character.format_skills(),
        "hp": character.vitals_label(),
        "max_hp": str(cap),
        "character_hp": character.vitals_label(),
        "character_max_hp": str(cap),
    }
