"""将多条系统/tool 事件压缩为更紧凑、带标签的聊天展示。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ROUTER_RE = re.compile(r"^结算路由：(.+?)（(.+?)）\s*$")
_NPC_RE = re.compile(r"^已记录 NPC：(.+?)（(.+?)）\s*$")
_FACT_RE = re.compile(r"^已记录关键事实：(.+)\s*$")
_TIME_RE = re.compile(
    r"^⏳\s*时间推进\s+(.+?)（(.+?)）(?:\s*[—–-]\s*(.+))?\s*$"
)
_SCENE_RE = re.compile(r"^场景已更新：(.+?)（(.+?)）\s*$")
_QUEST_RE = re.compile(r"^任务已更新：\[(.+?)\]\s*(.+?)（(.+?)）\s*$")
_ATTITUDE_RE = re.compile(r"^.+态度恶化：")
_NPC_BARE_RE = re.compile(
    r"^(.+?)（(?:neutral|friendly|hostile|unknown)）\s*$",
    re.IGNORECASE,
)

_CHECK_MARKERS = ("检定", "骰", "攻击", "伤害", "战斗", "掷骰", "重掷", "撤销", "vs DC")
_ALERT_MARKERS = ("⚠️", "❌", "支付失败", "行动无法执行", "跳过", "失败：")
_INVENTORY_MARKERS = (
    "获得：",
    "背包",
    "装备：",
    "持用：",
    "握持：",
    "卸下：",
    "使用：",
    "支付",
    "已补充描述",
)


@dataclass
class CompactSystemView:
    caption: str
    highlights: list[str] = field(default_factory=list)
    summary: str = ""
    details: list[str] = field(default_factory=list)
    show_expander: bool = False
    expander_label: str = "结算详情"


def format_tool_event_content(content: str) -> str:
    text = str(content).strip()
    if text.startswith("🎲 "):
        return text[2:].strip()
    return text


def format_tagged_line(tag: str, body: str) -> str:
    cleaned = body.strip()
    if not cleaned:
        return f"[{tag}]"
    if cleaned.startswith(f"[{tag}]"):
        return cleaned
    return f"[{tag}] {cleaned}"


def _strip_leading_emoji(text: str) -> str:
    return re.sub(r"^[📌⚠️❌✅⏰⏳😠🎲]\s*", "", text).strip()


def classify_event(text: str) -> tuple[str, str]:
    """返回 (标签, 正文)。"""
    cleaned = format_tool_event_content(text)
    if not cleaned:
        return "系统", ""

    router = _ROUTER_RE.match(cleaned)
    if router:
        return "路由", f"{router.group(1)} · {router.group(2)}"

    time_match = _TIME_RE.match(cleaned)
    if time_match:
        duration = time_match.group(1).strip()
        clock = time_match.group(2).strip()
        reason = (time_match.group(3) or "").strip()
        body = f"{clock}（+{duration}）"
        if reason:
            body = f"{body} — {reason}"
        return "时间", body

    if cleaned.startswith("⏰"):
        return "时限", _strip_leading_emoji(cleaned)

    scene = _SCENE_RE.match(cleaned)
    if scene:
        return "场景", f"{scene.group(1)}（{scene.group(2)}）"

    quest = _QUEST_RE.match(cleaned)
    if quest:
        return "任务", f"[{quest.group(1)}] {quest.group(2)}（{quest.group(3)}）"

    npc = _NPC_RE.match(cleaned)
    if npc:
        return "NPC", f"{npc.group(1)}（{npc.group(2)}）"

    bare_npc = _NPC_BARE_RE.match(cleaned)
    if bare_npc:
        return "NPC", cleaned

    fact = _FACT_RE.match(cleaned)
    if fact:
        return "记忆", fact.group(1).strip()

    if cleaned.startswith("📌") or cleaned.startswith("行动失败"):
        body = re.sub(r"^📌\s*行动失败：\s*", "", cleaned).strip()
        return "后果", body or _strip_leading_emoji(cleaned)

    if "检定" in cleaned or cleaned.startswith("🎲") or (
        "vs DC" in cleaned and "→" in cleaned
    ):
        return "检定", _strip_leading_emoji(cleaned)

    if cleaned.startswith("😠") or _ATTITUDE_RE.search(cleaned):
        return "关系", _strip_leading_emoji(cleaned)

    if cleaned.startswith("✅") or "后台完成" in cleaned:
        return "后台", _strip_leading_emoji(cleaned)

    if any(marker in cleaned for marker in _INVENTORY_MARKERS):
        return "物品", cleaned

    if cleaned.startswith("习得技能") or cleaned.startswith("失去技能") or cleaned.startswith("已拥有技能"):
        return "技能", cleaned

    if cleaned.startswith("❌") and "任务失败" in cleaned:
        return "任务", _strip_leading_emoji(cleaned)

    if any(marker in cleaned for marker in _ALERT_MARKERS):
        return "提示", _strip_leading_emoji(cleaned)

    if any(marker in cleaned for marker in _CHECK_MARKERS):
        return "检定", _strip_leading_emoji(cleaned)

    if cleaned.startswith("耗时说明："):
        return "时间", cleaned.removeprefix("耗时说明：").strip()

    return "记录", cleaned


def tagged_line(text: str) -> str:
    tag, body = classify_event(text)
    return format_tagged_line(tag, body)


def _event_kind(text: str) -> str:
    tag, _ = classify_event(text)
    mapping = {
        "路由": "router",
        "时间": "time",
        "时限": "time",
        "NPC": "npc",
        "记忆": "fact",
        "后果": "consequence",
        "提示": "alert",
        "检定": "check",
        "物品": "inventory",
        "技能": "skill",
        "场景": "scene",
        "任务": "quest",
        "关系": "consequence",
        "后台": "other",
        "记录": "other",
    }
    return mapping.get(tag, "other")


def _system_caption(events: list[str]) -> str:
    kinds = {_event_kind(format_tool_event_content(event)) for event in events}
    if "alert" in kinds:
        return "系统 · 提示"
    if ("check" in kinds or "consequence" in kinds) and kinds - {
        "check",
        "consequence",
        "router",
    }:
        return "系统 · 回合"
    if "check" in kinds or "consequence" in kinds:
        return "系统 · 检定/战斗"
    if "router" in kinds:
        return "系统 · 结算"
    return "系统 · 结算"


def compact_system_events(events: list[str]) -> CompactSystemView:
    cleaned_events = [format_tool_event_content(event) for event in events if str(event).strip()]
    if not cleaned_events:
        return CompactSystemView(caption="系统 · 结算")

    if len(cleaned_events) == 1:
        line = tagged_line(cleaned_events[0])
        kind = _event_kind(cleaned_events[0])
        if kind in {"check", "alert"}:
            return CompactSystemView(
                caption=_system_caption(cleaned_events),
                highlights=[line],
            )
        return CompactSystemView(
            caption=_system_caption(cleaned_events),
            summary=f"*{line}*",
        )

    highlights: list[str] = []
    details: list[str] = []
    summary_parts: list[str] = []
    time_lines: list[str] = []
    npc_count = 0
    fact_count = 0
    inventory_count = 0
    has_router = False

    for text in cleaned_events:
        tag, body = classify_event(text)
        kind = _event_kind(text)
        line = format_tagged_line(tag, body)

        if kind in {"check", "consequence"} and tag in {"检定", "后果", "关系"}:
            highlights.append(line)
            continue

        if tag in {"提示"} or (kind == "alert"):
            highlights.append(line)
            continue

        if tag == "时间":
            time_lines.append(line)
            continue

        if tag == "路由":
            has_router = True
            details.append(line)
            continue

        if tag == "NPC":
            npc_count += 1
            details.append(line)
            continue

        if tag == "记忆":
            fact_count += 1
            details.append(line)
            continue

        if tag == "物品":
            inventory_count += 1
            details.append(line)
            continue

        if tag in {"场景", "任务", "技能", "后台", "时限", "记录"}:
            details.append(line)
            continue

        if kind == "check":
            highlights.append(line)
            continue

        details.append(line)

    if time_lines:
        summary_parts.append(time_lines[0])
        for extra in time_lines[1:]:
            details.append(extra)

    if npc_count:
        summary_parts.append(f"[NPC] ×{npc_count}")
    if fact_count:
        summary_parts.append(f"[记忆] ×{fact_count}")
    if inventory_count:
        summary_parts.append(f"[物品] ×{inventory_count}")
    if not summary_parts and details:
        summary_parts.append(f"[变更] ×{len(details)}")

    summary = " · ".join(summary_parts)
    show_expander = bool(details) and (
        len(details) >= 2
        or has_router
        or any(len(line) > 56 for line in details)
        or (not highlights and len(cleaned_events) > 1)
    )

    if details and not show_expander and not highlights:
        return CompactSystemView(
            caption=_system_caption(cleaned_events),
            summary=summary,
            details=details,
        )

    return CompactSystemView(
        caption=_system_caption(cleaned_events),
        highlights=highlights,
        summary=summary,
        details=details if show_expander else [],
        show_expander=show_expander,
    )
