"""将多条系统/tool 事件压缩为更紧凑的聊天展示。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ROUTER_RE = re.compile(r"^结算路由：(.+?)（(.+?)）\s*$")
_NPC_RE = re.compile(r"^已记录 NPC：(.+?)（(.+?)）\s*$")
_FACT_RE = re.compile(r"^已记录关键事实：(.+)\s*$")
_TIME_RE = re.compile(
    r"^⏳\s*时间推进\s+(.+?)（(.+?)）(?:\s*[—–-]\s*(.+))?\s*$"
)

_CHECK_MARKERS = ("检定", "骰", "攻击", "伤害", "战斗", "掷骰", "重掷", "撤销")
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


def _event_kind(text: str) -> str:
    if text.startswith("结算路由"):
        return "router"
    if _TIME_RE.match(text) or text.startswith("⏰"):
        return "time"
    if _NPC_RE.match(text):
        return "npc"
    if _FACT_RE.match(text):
        return "fact"
    if any(marker in text for marker in _ALERT_MARKERS):
        return "alert"
    if any(marker in text for marker in _CHECK_MARKERS) or text.startswith("🎲"):
        return "check"
    if any(marker in text for marker in _INVENTORY_MARKERS):
        return "inventory"
    return "other"


def _system_caption(events: list[str]) -> str:
    kinds = {_event_kind(format_tool_event_content(event)) for event in events}
    if "alert" in kinds:
        return "系统 · 提示"
    if "check" in kinds and kinds - {"check", "router"}:
        return "系统 · 回合"
    if "check" in kinds:
        return "系统 · 检定/战斗"
    if "router" in kinds:
        return "系统 · 结算"
    return "系统 · 结算"


def _short_time_line(text: str) -> str:
    match = _TIME_RE.match(text)
    if not match:
        return text
    duration, clock, reason = match.group(1).strip(), match.group(2).strip(), (match.group(3) or "").strip()
    line = f"⏳ {clock}（+{duration}）"
    if reason and len(reason) <= 36:
        line = f"{line} — {reason}"
    elif reason:
        line = f"{line} — {reason[:33]}…"
    return line


def _detail_line(text: str) -> str:
    cleaned = format_tool_event_content(text)
    router = _ROUTER_RE.match(cleaned)
    if router:
        return f"路由 {router.group(1)} · {router.group(2)}"
    npc = _NPC_RE.match(cleaned)
    if npc:
        return f"{npc.group(1)}（{npc.group(2)}）"
    fact = _FACT_RE.match(cleaned)
    if fact:
        return fact.group(1).strip()
    time_match = _TIME_RE.match(cleaned)
    if time_match and time_match.group(3):
        return f"耗时说明：{time_match.group(3).strip()}"
    return cleaned


def compact_system_events(events: list[str]) -> CompactSystemView:
    cleaned_events = [format_tool_event_content(event) for event in events if str(event).strip()]
    if not cleaned_events:
        return CompactSystemView(caption="系统 · 结算")

    if len(cleaned_events) == 1:
        text = cleaned_events[0]
        kind = _event_kind(text)
        if kind in {"check", "alert"}:
            return CompactSystemView(
                caption=_system_caption(cleaned_events),
                highlights=[text],
            )
        if kind == "time":
            return CompactSystemView(
                caption=_system_caption(cleaned_events),
                summary=_short_time_line(text),
            )
        return CompactSystemView(
            caption=_system_caption(cleaned_events),
            summary=text,
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
        kind = _event_kind(text)
        if kind in {"check", "alert"}:
            highlights.append(text)
            continue
        if kind == "time":
            time_lines.append(_short_time_line(text))
            time_match = _TIME_RE.match(text)
            if time_match and time_match.group(3):
                details.append(f"耗时说明：{time_match.group(3).strip()}")
            continue
        if kind == "router":
            has_router = True
            details.append(_detail_line(text))
            continue
        if kind == "npc":
            npc_count += 1
            details.append(_detail_line(text))
            continue
        if kind == "fact":
            fact_count += 1
            details.append(_detail_line(text))
            continue
        if kind == "inventory":
            inventory_count += 1
            details.append(_detail_line(text))
            continue
        details.append(_detail_line(text))

    if time_lines:
        summary_parts.append(time_lines[0])
        for extra in time_lines[1:]:
            details.append(extra)
    if npc_count:
        summary_parts.append(f"NPC×{npc_count}")
    if fact_count:
        summary_parts.append(f"记忆×{fact_count}")
    if inventory_count:
        summary_parts.append(f"物品×{inventory_count}")
    if not summary_parts and details:
        summary_parts.append(f"变更×{len(details)}")

    summary = " · ".join(summary_parts)
    show_expander = bool(details) and (
        len(details) >= 2
        or has_router
        or any(len(line) > 48 for line in details)
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
