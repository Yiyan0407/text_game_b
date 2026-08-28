"""叙事时间轴：故事内时钟、行动耗时估算与时限触发。"""

from __future__ import annotations

import re
import uuid

from game.models import GameState, NarrativeDeadline
from game.results import ActionRouteResult, DeadlinePatch, TimePatch

_STORY_DAY_MINUTES = 24 * 60
_DEFAULT_START_MINUTE = 8 * 60  # 第1天 08:00
_IMMINENT_MINUTES = 30


def format_clock(elapsed_minutes: int) -> str:
    absolute = _DEFAULT_START_MINUTE + max(0, elapsed_minutes)
    day = absolute // _STORY_DAY_MINUTES + 1
    minute_of_day = absolute % _STORY_DAY_MINUTES
    hour, minute = divmod(minute_of_day, 60)
    return f"第{day}天 {hour:02d}:{minute:02d}"


def narrative_time_display(game_state: GameState) -> str:
    if game_state.narrative_time_label.strip():
        return game_state.narrative_time_label.strip()
    return format_clock(game_state.elapsed_minutes)


def format_duration(minutes: int) -> str:
    minutes = max(0, int(minutes))
    if minutes >= _STORY_DAY_MINUTES and minutes % _STORY_DAY_MINUTES == 0:
        days = minutes // _STORY_DAY_MINUTES
        return f"{days} 天"
    if minutes >= 60:
        hours, mins = divmod(minutes, 60)
        if mins:
            return f"{hours} 小时 {mins} 分"
        return f"{hours} 小时"
    return f"{minutes} 分"


_NUM_TOKEN = r"(?:\d+|[一二三四五六七八九十两]+)"


def _parse_count_token(text: str) -> int | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.isdigit():
        return int(stripped)
    mapping = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if stripped in mapping:
        return mapping[stripped]
    if stripped.startswith("十") and len(stripped) == 2 and stripped[1] in mapping:
        return 10 + mapping[stripped[1]]
    return None


def parse_explicit_wait_minutes(text: str, *, elapsed_minutes: int) -> int | None:
    normalized = text.strip()
    if not normalized:
        return None

    patterns: list[tuple[re.Pattern[str], str]] = [
        (re.compile(rf"(?:等|等待|睡|过)(?:上)?({_NUM_TOKEN})\s*天"), "days"),
        (re.compile(rf"(?:等|等待)(?:上)?({_NUM_TOKEN})\s*个?\s*小时"), "hours"),
        (re.compile(rf"(?:等|等待)(?:上)?({_NUM_TOKEN})\s*分钟"), "minutes"),
        (re.compile(r"(?:等|等待)(?:到)?(?:明天|翌日|天亮)"), "tomorrow"),
        (re.compile(r"过夜|睡一夜|休整一夜|休息一(?:夜|晚)"), "overnight"),
    ]
    for pattern, unit in patterns:
        match = pattern.search(normalized)
        if not match:
            continue
        if unit == "tomorrow":
            absolute = _DEFAULT_START_MINUTE + elapsed_minutes
            minute_of_day = absolute % _STORY_DAY_MINUTES
            until_morning = (_STORY_DAY_MINUTES - minute_of_day) % _STORY_DAY_MINUTES
            return max(60, until_morning or _STORY_DAY_MINUTES)
        if unit == "overnight":
            return 8 * 60
        count = _parse_count_token(match.group(1))
        if count is None:
            continue
        if unit == "days":
            return count * _STORY_DAY_MINUTES
        if unit == "hours":
            return count * 60
        return count
    return None


def estimate_turn_minutes(
    route: ActionRouteResult | None,
    user_input: str,
    game_state: GameState,
) -> int:
    explicit = parse_explicit_wait_minutes(user_input, elapsed_minutes=game_state.elapsed_minutes)
    if explicit is not None:
        return explicit

    text = user_input.strip()
    intent = route.action_intent.strip() if route else ""
    combined = f"{intent} {text}"

    if game_state.is_in_combat():
        return 6

    if route and route.trigger_combat:
        return 5

    long_wait_markers = ("整晚", "半天", "一整天", "一天", "数日")
    if any(marker in combined for marker in long_wait_markers):
        if "半天" in combined:
            return 12 * 60
        if "一天" in combined or "整日" in combined:
            return _STORY_DAY_MINUTES
        if "数日" in combined:
            return 2 * _STORY_DAY_MINUTES

    travel_markers = ("长途", "跨城", "赶到", "前往", "驱车", "飞行", "坐火车", "转场")
    if any(marker in combined for marker in travel_markers):
        return 45

    scene_markers = ("进入", "离开", "返回", "赶到", "抵达")
    if any(marker in combined for marker in scene_markers):
        return 25

    search_markers = ("搜查", "搜证", "排查", "全面调查", "翻找")
    if any(marker in combined for marker in search_markers):
        return 30

    talk_markers = ("交谈", "对话", "询问", "商量", "谈判", "闲聊")
    if any(marker in combined for marker in talk_markers):
        return 10

    quick_markers = ("观察", "查看", "检查", "倾听", "偷听", "阅读")
    if any(marker in combined for marker in quick_markers):
        return 5

    if route and route.item_usage == "purchase":
        return 15

    return 12


def _deadline_remaining(deadline: NarrativeDeadline, elapsed_minutes: int) -> int:
    return deadline.due_at_minutes - elapsed_minutes


def _ensure_deadline_id(label: str, proposed: str, existing_ids: set[str]) -> str:
    if proposed.strip():
        base = proposed.strip()
    else:
        slug = re.sub(r"\s+", "_", label.strip())[:24] or "deadline"
        base = slug
    if base not in existing_ids:
        return base
    return f"{base}_{uuid.uuid4().hex[:6]}"


def add_deadline(game_state: GameState, patch: DeadlinePatch) -> list[str]:
    label = patch.label.strip()
    if not label:
        return []

    existing_ids = {item.id for item in game_state.deadlines}
    deadline_id = _ensure_deadline_id(label, patch.id, existing_ids)

    if patch.due_at_minutes is not None and patch.due_at_minutes >= 0:
        due_at = int(patch.due_at_minutes)
    else:
        due_in = max(1, int(patch.due_in_minutes or 0))
        due_at = game_state.elapsed_minutes + due_in

    game_state.deadlines.append(
        NarrativeDeadline(
            id=deadline_id,
            label=label,
            due_at_minutes=due_at,
            status="pending",
            consequence=patch.consequence.strip(),
            created_at_minutes=game_state.elapsed_minutes,
        )
    )
    remaining = _deadline_remaining(game_state.deadlines[-1], game_state.elapsed_minutes)
    return [
        f"⏰ 已登记时限：{label}（{format_duration(remaining)}后 / {narrative_time_display_at(game_state, due_at)}）"
    ]


def narrative_time_display_at(game_state: GameState, due_at_minutes: int) -> str:
    saved = game_state.elapsed_minutes
    try:
        game_state.elapsed_minutes = due_at_minutes
        return narrative_time_display(game_state)
    finally:
        game_state.elapsed_minutes = saved


def cancel_deadline(game_state: GameState, deadline_id: str) -> str | None:
    target_id = deadline_id.strip()
    if not target_id:
        return None
    for deadline in game_state.deadlines:
        if deadline.id == target_id and deadline.status == "pending":
            deadline.status = "cancelled"
            return f"⏰ 已取消时限：{deadline.label}"
    return None


def _trigger_deadline(game_state: GameState, deadline: NarrativeDeadline) -> list[str]:
    from config.settings import get_settings

    deadline.status = "triggered"
    overdue = format_duration(max(0, game_state.elapsed_minutes - deadline.due_at_minutes))
    events = [f"⏰ 时限已到：{deadline.label}（逾期 {overdue}）"]
    fact = f"时限「{deadline.label}」已到期"
    if deadline.consequence.strip():
        fact = f"{fact}；后果：{deadline.consequence.strip()}"
    game_state.add_memory_facts([fact], get_settings().max_memory_facts)
    return events


def advance_narrative_clock(game_state: GameState, minutes: int) -> list[str]:
    if minutes <= 0:
        return check_imminent_deadlines(game_state)

    before = game_state.elapsed_minutes
    game_state.elapsed_minutes += minutes
    if not game_state.narrative_time_label.strip():
        game_state.narrative_time_label = format_clock(game_state.elapsed_minutes)
    else:
        game_state.narrative_time_label = format_clock(game_state.elapsed_minutes)

    events = [
        f"⏳ 时间推进 {format_duration(minutes)}（{narrative_time_display(game_state)}）"
    ]
    for deadline in game_state.deadlines:
        if deadline.status != "pending":
            continue
        if deadline.due_at_minutes > before and deadline.due_at_minutes <= game_state.elapsed_minutes:
            events.extend(_trigger_deadline(game_state, deadline))
    events.extend(check_imminent_deadlines(game_state))
    return events


def check_imminent_deadlines(game_state: GameState) -> list[str]:
    events: list[str] = []
    for deadline in game_state.deadlines:
        if deadline.status != "pending":
            continue
        remaining = _deadline_remaining(deadline, game_state.elapsed_minutes)
        if remaining < 0:
            events.extend(_trigger_deadline(game_state, deadline))
        elif remaining <= _IMMINENT_MINUTES:
            events.append(
                f"⏰ 时限临近：{deadline.label}（还剩 {format_duration(remaining)}）"
            )
    return events


def apply_time_patch(game_state: GameState, patch: TimePatch | None) -> list[str]:
    if patch is None:
        return []

    events: list[str] = []
    if patch.time_label.strip():
        game_state.narrative_time_label = patch.time_label.strip()

    for deadline_id in patch.cancel_deadline_ids:
        message = cancel_deadline(game_state, deadline_id)
        if message:
            events.append(message)

    for deadline_patch in patch.deadlines:
        events.extend(add_deadline(game_state, deadline_patch))

    if patch.advance_minutes > 0:
        events.extend(advance_narrative_clock(game_state, patch.advance_minutes))

    return events


def format_narrative_time_context(game_state: GameState) -> str:
    lines = [
        f"当前故事内时间：{narrative_time_display(game_state)}",
        f"自开场以来已过去：{format_duration(game_state.elapsed_minutes)}",
    ]

    pending = [d for d in game_state.deadlines if d.status == "pending"]
    if pending:
        lines.append("待兑现时限（叙事不得与之矛盾）：")
        for deadline in pending:
            remaining = _deadline_remaining(deadline, game_state.elapsed_minutes)
            if remaining < 0:
                lines.append(
                    f"- {deadline.label}：已逾期 {format_duration(-remaining)}，"
                    "本轮必须体现后果，不得再写「还有很久」"
                )
            elif remaining == 0:
                lines.append(f"- {deadline.label}：此刻到期")
            else:
                lines.append(
                    f"- {deadline.label}：还剩 {format_duration(remaining)}"
                    f"（约 {narrative_time_display_at(game_state, deadline.due_at_minutes)}）"
                )
                if deadline.consequence.strip():
                    lines.append(f"  到期后果：{deadline.consequence.strip()}")

    triggered = [d for d in game_state.deadlines if d.status == "triggered"][-3:]
    if triggered:
        lines.append("近期已触发时限：")
        for deadline in triggered:
            lines.append(f"- {deadline.label}")

    return "\n".join(lines)


def format_time_constraints_for_kp(game_state: GameState) -> str:
    pending = [d for d in game_state.deadlines if d.status == "pending"]
    overdue = [
        d for d in pending if _deadline_remaining(d, game_state.elapsed_minutes) < 0
    ]
    imminent = [
        d
        for d in pending
        if 0 <= _deadline_remaining(d, game_state.elapsed_minutes) <= _IMMINENT_MINUTES
    ]
    if not overdue and not imminent:
        return ""

    lines = ["【时限约束 — 本轮叙事必须遵守】"]
    for deadline in overdue:
        lines.append(
            f"- 「{deadline.label}」已过期：必须写到期后果，禁止假装尚未发生。"
        )
        if deadline.consequence.strip():
            lines.append(f"  建议后果：{deadline.consequence.strip()}")
    for deadline in imminent:
        remaining = _deadline_remaining(deadline, game_state.elapsed_minutes)
        lines.append(
            f"- 「{deadline.label}」仅剩 {format_duration(remaining)}：须体现紧迫，勿再拖延。"
        )
    lines.append(
        "禁止出现与【叙事时间】矛盾的表述（如已过去数小时却仍写「还有六小时才开始」）。"
    )
    return "\n".join(lines)


def advance_narrative_time_for_turn(
    route: ActionRouteResult | None,
    user_input: str,
    game_state: GameState,
) -> list[str]:
    minutes = estimate_turn_minutes(route, user_input, game_state)
    return advance_narrative_clock(game_state, minutes)
