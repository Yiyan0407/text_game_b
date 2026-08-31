"""叙事时间轴：故事内时钟与时限触发。"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from game.models import GameState, NarrativeDeadline
from game.results import ActionRouteResult, DeadlinePatch, TimePatch

if TYPE_CHECKING:
    from game.models import Character
    from game.scenario import Scenario

_STORY_DAY_MINUTES = 24 * 60
_DEFAULT_START_MINUTE = 8 * 60  # 第1天 08:00
_IMMINENT_MINUTES = 30
_TIME_ADVANCE_RE = re.compile(r"时间推进\s+(.+?)（")
_CLOCK_LABEL_RE = re.compile(r"第(\d+)天\s*(\d{1,2}):(\d{2})")
_DAY_TIME_RE = re.compile(r"第(\d+)天\s*(\d{1,2})[:：点时](\d{1,2})")
_NOW_CLOCK_ANCHOR_RES: list[tuple[re.Pattern[str], bool]] = [
    (
        re.compile(
            r"(?:时间显示|当前时间|现在是|此时|钟表显示|表盘显示|时钟显示|看了(?:看)?(?:表|时间))"
            r"[：:\s]*"
            r"(?:(凌晨|清晨|早上|上午|中午|午后|下午|傍晚|晚上|深夜)\s*)?"
            r"(\d{1,2})\s*[:：点时]\s*(\d{1,2})\s*分?"
        ),
        True,
    ),
    (
        re.compile(
            r"(?:(凌晨|清晨|早上|上午|中午|午后|下午|傍晚|晚上|深夜)\s*)?"
            r"(\d{1,2})\s*[:：点时]\s*(\d{1,2})\s*分?"
            r"(?!\s*(?:到|至|—|–|-|\~))"
        ),
        False,
    ),
]
_PERIOD_HOUR_OFFSET = {
    "下午": 12,
    "午后": 12,
    "傍晚": 12,
    "晚上": 12,
    "深夜": 0,
}


def parse_time_label(label: str) -> tuple[int, int, int] | None:
    match = _CLOCK_LABEL_RE.search(label.strip())
    if not match:
        return None
    day = max(1, int(match.group(1)))
    hour = min(23, max(0, int(match.group(2))))
    minute = min(59, max(0, int(match.group(3))))
    return day, hour, minute


def absolute_minutes_from_day_time(day: int, hour: int, minute: int) -> int:
    return (max(1, day) - 1) * _STORY_DAY_MINUTES + hour * 60 + minute


def format_clock(elapsed_minutes: int, story_start_absolute: int = _DEFAULT_START_MINUTE) -> str:
    absolute = story_start_absolute + max(0, elapsed_minutes)
    day = absolute // _STORY_DAY_MINUTES + 1
    minute_of_day = absolute % _STORY_DAY_MINUTES
    hour, minute = divmod(minute_of_day, 60)
    return f"第{day}天 {hour:02d}:{minute:02d}"


def narrative_time_display(game_state: GameState) -> str:
    label = game_state.narrative_time_label.strip()
    parsed = parse_time_label(label) if label else None
    if parsed is None and label:
        return label
    return format_clock(
        game_state.elapsed_minutes,
        game_state.story_start_absolute_minutes,
    )


def initialize_story_clock_from_scenario(game_state: GameState, scenario: Scenario) -> None:
    """开场时钟由 State Agent 的 time.time_label 写入，此处不做推断。"""
    del scenario
    return


def current_absolute_minutes(game_state: GameState) -> int:
    return game_state.story_start_absolute_minutes + max(0, game_state.elapsed_minutes)


def reanchor_story_clock(
    game_state: GameState,
    day: int,
    hour: int,
    minute: int,
    *,
    elapsed_minutes: int = 0,
) -> None:
    absolute = absolute_minutes_from_day_time(day, hour, minute)
    game_state.story_start_absolute_minutes = absolute
    game_state.elapsed_minutes = max(0, int(elapsed_minutes))
    game_state.narrative_time_label = format_clock(
        game_state.elapsed_minutes,
        game_state.story_start_absolute_minutes,
    )


def _normalize_clock_hour(period: str, hour: int) -> int:
    hour = min(23, max(0, hour))
    if period in {"下午", "午后", "傍晚", "晚上"} and hour < 12:
        hour += 12
    if period == "中午" and hour < 11:
        hour += 12
    return hour


def extract_explicit_current_clock(text: str) -> tuple[int, int, int] | None:
    """从 KP 叙事中提取「当前时刻」；忽略排班表等区间描述。"""
    normalized = text.strip()
    if not normalized:
        return None

    day_match = _DAY_TIME_RE.search(normalized)
    if day_match:
        return (
            max(1, int(day_match.group(1))),
            min(23, max(0, int(day_match.group(2)))),
            min(59, max(0, int(day_match.group(3)))),
        )

    for pattern, _ in _NOW_CLOCK_ANCHOR_RES:
        match = pattern.search(normalized)
        if not match:
            continue
        groups = match.groups()
        if len(groups) == 3:
            period, hour_raw, minute_raw = groups
        else:
            period, hour_raw, minute_raw = "", groups[0], groups[1]
        hour = _normalize_clock_hour(period or "", int(hour_raw))
        minute = min(59, max(0, int(minute_raw)))
        return 1, hour, minute
    return None


def reconcile_clock_from_kp_narrative(
    game_state: GameState,
    kp_text: str,
    *,
    tolerance_minutes: int = 20,
    extra_elapsed: int = 0,
) -> list[str]:
    """KP 叙事若明确写出当前时刻，与系统钟相差过大时重锚定（如穿越后仍为默认 08:00）。"""
    parsed = extract_explicit_current_clock(kp_text)
    if parsed is None:
        return []

    day, hour, minute = parsed
    target = absolute_minutes_from_day_time(day, hour, minute) + max(0, extra_elapsed)
    current = current_absolute_minutes(game_state)
    if abs(target - current) <= tolerance_minutes:
        return []

    before_label = narrative_time_display(game_state)
    reanchor_story_clock(
        game_state,
        day,
        hour,
        minute,
        elapsed_minutes=max(0, extra_elapsed),
    )
    after_label = narrative_time_display(game_state)
    return [
        f"⏳ 叙事时间校正 {before_label} → {after_label}（与 KP 叙事中的当前时刻对齐）"
    ]


def apply_story_clock_label(game_state: GameState, label: str) -> None:
    parsed = parse_time_label(label)
    if parsed is None:
        game_state.narrative_time_label = label.strip()
        return

    day, hour, minute = parsed
    absolute = absolute_minutes_from_day_time(day, hour, minute)
    current = current_absolute_minutes(game_state)
    if game_state.turn_count == 0 and game_state.elapsed_minutes == 0:
        reanchor_story_clock(game_state, day, hour, minute, elapsed_minutes=0)
        return
    if abs(absolute - current) > 20 or absolute < game_state.story_start_absolute_minutes:
        reanchor_story_clock(game_state, day, hour, minute, elapsed_minutes=0)
        return
    game_state.elapsed_minutes = max(0, absolute - game_state.story_start_absolute_minutes)
    game_state.narrative_time_label = format_clock(
        game_state.elapsed_minutes,
        game_state.story_start_absolute_minutes,
    )


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


def parse_explicit_wait_minutes(
    text: str,
    *,
    elapsed_minutes: int,
    story_start_absolute: int = _DEFAULT_START_MINUTE,
) -> int | None:
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
            absolute = story_start_absolute + elapsed_minutes
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


def _explicit_wait_reason(text: str) -> str:
    normalized = text.strip()
    if re.search(r"(?:等|等待)(?:到)?(?:明天|翌日|天亮)", normalized):
        return "等待至次日/天亮（玩家声明）"
    if re.search(r"过夜|睡一夜|休整一夜|休息一(?:夜|晚)", normalized):
        return "过夜休息（玩家声明）"
    if re.search(rf"(?:等|等待)(?:上)?{_NUM_TOKEN}\s*天", normalized):
        return "多日等待（玩家声明）"
    if re.search(rf"(?:等|等待)(?:上)?{_NUM_TOKEN}\s*个?\s*小时", normalized):
        return "数小时等待（玩家声明）"
    if re.search(rf"(?:等|等待)(?:上)?{_NUM_TOKEN}\s*分钟", normalized):
        return "短时等待（玩家声明）"
    return "等待/休息（玩家声明）"


def format_time_advance_event(minutes: int, clock_label: str, reason: str = "") -> str:
    base = f"⏳ 时间推进 {format_duration(minutes)}（{clock_label}）"
    cleaned = reason.strip()
    if cleaned:
        return f"{base} — {cleaned}"
    return base


def extract_turn_time_cost(mechanical_events: list[str]) -> str | None:
    """从机械事件里解析本轮推进的耗时文案。"""
    for event in mechanical_events:
        match = _TIME_ADVANCE_RE.search(event)
        if match:
            return match.group(1).strip()
    return None


def format_turn_time_hint(mechanical_events: list[str]) -> str:
    cost = extract_turn_time_cost(mechanical_events)
    if not cost:
        return ""
    return (
        f"【本轮故事耗时】约 {cost}（已由状态同步器判定并已推进时钟；"
        "叙事中此轮经过的时间须与此同量级，勿写成数小时。）"
    )


def _deadline_remaining(deadline: NarrativeDeadline, elapsed_minutes: int) -> int:
    return deadline.due_at_minutes - elapsed_minutes


def _deadline_is_due(deadline: NarrativeDeadline) -> bool:
    return deadline.status in ("due", "triggered")


def _deadline_is_open(deadline: NarrativeDeadline) -> bool:
    return deadline.status == "pending" or _deadline_is_due(deadline)


def _ensure_deadline_id(label: str, proposed: str, existing_ids: set[str]) -> str:
    if proposed.strip():
        base = proposed.strip()
    else:
        slug = re.sub(r"\s+", "_", label.strip())[:24] or "deadline"
        base = slug
    if base not in existing_ids:
        return base
    return f"{base}_{uuid.uuid4().hex[:6]}"


def parse_stated_action_minutes(text: str) -> int | None:
    """解析玩家声明的本轮行动耗时（如「15分钟完成植入」）。"""
    normalized = text.strip()
    if not normalized:
        return None
    patterns = [
        re.compile(rf"(?:需要|花|用|给我|耗时)\s*({_NUM_TOKEN})\s*分钟"),
        re.compile(rf"(?:在|于)\s*({_NUM_TOKEN})\s*分钟内"),
        re.compile(rf"({_NUM_TOKEN})\s*分钟内"),
    ]
    for pattern in patterns:
        match = pattern.search(normalized)
        if not match:
            continue
        count = _parse_count_token(match.group(1))
        if count is not None:
            return count
    return None


def add_deadline(game_state: GameState, patch: DeadlinePatch) -> list[str]:
    label = patch.label.strip()
    if not label:
        return []

    for existing in game_state.deadlines:
        if existing.status == "pending" and existing.label == label:
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
            fail_quest_ids=list(patch.fail_quest_ids),
            hp_loss=max(0, int(patch.hp_loss or 0)),
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
    target = deadline_id.strip()
    if not target:
        return None
    deadline = _find_open_deadline(game_state, target)
    if deadline is None:
        return None
    was_due = _deadline_is_due(deadline)
    deadline.status = "cancelled"
    if was_due:
        return f"⏰ 已化解时限：{deadline.label}"
    return f"⏰ 已取消时限：{deadline.label}"


def enforce_deadline(
    game_state: GameState,
    deadline_id: str,
    character: Character | None = None,
) -> list[str]:
    target = deadline_id.strip()
    if not target:
        return []
    deadline = _find_due_deadline(game_state, target)
    if deadline is None:
        pending = _find_open_deadline(game_state, target)
        if (
            pending is not None
            and pending.status == "pending"
            and _deadline_remaining(pending, game_state.elapsed_minutes) <= 0
        ):
            _trigger_deadline(game_state, pending, character)
            deadline = pending if _deadline_is_due(pending) else None
    if deadline is None:
        return []
    deadline.status = "resolved"
    events = [f"⏰ 时限后果成立：{deadline.label}"]
    events.extend(_apply_deadline_penalties(game_state, deadline, character))
    return events


def _find_open_deadline(game_state: GameState, ref: str) -> NarrativeDeadline | None:
    for deadline in game_state.deadlines:
        if not _deadline_is_open(deadline):
            continue
        if deadline.id == ref or deadline.label == ref:
            return deadline
    return None


def _find_due_deadline(game_state: GameState, ref: str) -> NarrativeDeadline | None:
    for deadline in game_state.deadlines:
        if not _deadline_is_due(deadline):
            continue
        if deadline.id == ref or deadline.label == ref:
            return deadline
    return None


def _resolve_fail_quest_ids(
    deadline: NarrativeDeadline,
    game_state: GameState,
) -> list[str]:
    quest_ids = [quest_id.strip() for quest_id in deadline.fail_quest_ids if quest_id.strip()]
    seen = set(quest_ids)

    if deadline.id.strip() and deadline.id.strip() not in seen:
        for quest in game_state.active_quests:
            if quest.status == "active" and quest.id == deadline.id.strip():
                quest_ids.append(quest.id)
                seen.add(quest.id)
                break

    label = deadline.label.strip()
    if label:
        for quest in game_state.active_quests:
            if quest.status != "active" or quest.id in seen:
                continue
            if label in quest.title or label in quest.description:
                quest_ids.append(quest.id)
                seen.add(quest.id)

    return quest_ids


def _default_hp_loss(configured: int) -> int:
    return max(0, int(configured or 0))


def _apply_deadline_penalties(
    game_state: GameState,
    deadline: NarrativeDeadline,
    character: Character | None,
) -> list[str]:
    events: list[str] = []
    for quest_id in _resolve_fail_quest_ids(deadline, game_state):
        quest = game_state.get_quest(quest_id)
        if quest is None or quest.status != "active":
            continue
        quest.status = "failed"
        events.append(f"❌ 任务失败：[{quest.id}] {quest.title}")

    hp_loss = _default_hp_loss(deadline.hp_loss)
    if character is not None and hp_loss > 0:
        from game.effect_resolver import apply_incoming_damage

        before = character.hp
        result = apply_incoming_damage(character, hp_loss)
        if character.hp < 1:
            character.hp = 1
        if result.fully_blocked and result.effective_sp > 0:
            events.append(
                f"🛡️ 时限后果：SP{result.effective_sp} 完全挡住 {hp_loss} 点伤害"
            )
        else:
            actual = before - character.hp
            if actual > 0:
                events.extend(result.format_events())
                events.append(
                    f"💔 时限后果：受到 {actual} 点伤害（HP {character.hp}/{character.effective_max_hp()}）"
                )

    return events


def _trigger_deadline(
    game_state: GameState,
    deadline: NarrativeDeadline,
    character: Character | None = None,
) -> list[str]:
    from config.settings import get_settings

    if _deadline_is_due(deadline):
        return []

    deadline.status = "due"
    overdue = format_duration(max(0, game_state.elapsed_minutes - deadline.due_at_minutes))
    events = [f"⏰ 时限已到：{deadline.label}（逾期 {overdue}，待叙事裁定后果）"]
    fact = f"时限「{deadline.label}」已到期，后果是否发生须结合剧情裁定"
    if deadline.consequence.strip():
        fact = f"{fact}；若未能阻止，可能后果：{deadline.consequence.strip()}"
    game_state.add_memory_facts([fact], get_settings().max_memory_facts)
    return events


def advance_narrative_clock(
    game_state: GameState,
    minutes: int,
    character: Character | None = None,
    *,
    reason: str = "",
) -> list[str]:
    if minutes <= 0:
        return check_imminent_deadlines(game_state, character=character)

    before = game_state.elapsed_minutes
    game_state.elapsed_minutes += minutes
    game_state.narrative_time_label = format_clock(
        game_state.elapsed_minutes,
        game_state.story_start_absolute_minutes,
    )

    events = [
        format_time_advance_event(
            minutes,
            narrative_time_display(game_state),
            reason,
        )
    ]
    for deadline in game_state.deadlines:
        if deadline.status != "pending":
            continue
        if deadline.due_at_minutes > before and deadline.due_at_minutes <= game_state.elapsed_minutes:
            events.extend(_trigger_deadline(game_state, deadline, character))
    events.extend(check_imminent_deadlines(game_state, character=character))
    from game.background_process import resolve_background_processes

    events.extend(resolve_background_processes(game_state))
    return events


def check_imminent_deadlines(
    game_state: GameState,
    character: Character | None = None,
) -> list[str]:
    events: list[str] = []
    for deadline in game_state.deadlines:
        if deadline.status != "pending":
            continue
        remaining = _deadline_remaining(deadline, game_state.elapsed_minutes)
        if remaining < 0:
            events.extend(_trigger_deadline(game_state, deadline, character))
        elif remaining <= _IMMINENT_MINUTES:
            events.append(
                f"⏰ 时限临近：{deadline.label}（还剩 {format_duration(remaining)}）"
            )
    return events


def apply_time_patch(
    game_state: GameState,
    patch: TimePatch | None,
    character: Character | None = None,
) -> list[str]:
    if patch is None:
        return []

    events: list[str] = []

    for deadline_id in patch.cancel_deadline_ids:
        message = cancel_deadline(game_state, deadline_id)
        if message:
            events.append(message)
        else:
            events.append(f"⚠️ 未找到可取消/化解的时限：{deadline_id.strip()}")

    for deadline_id in patch.enforce_deadline_ids:
        enforced = enforce_deadline(game_state, deadline_id, character)
        if enforced:
            events.extend(enforced)
        else:
            events.append(f"⚠️ 未找到可执行后果的时限：{deadline_id.strip()}")

    for deadline_patch in patch.deadlines:
        events.extend(add_deadline(game_state, deadline_patch))

    if patch.advance_minutes > 0:
        events.extend(
            advance_narrative_clock(
                game_state,
                patch.advance_minutes,
                character,
                reason=patch.advance_reason,
            )
        )
    elif patch.time_label.strip():
        apply_story_clock_label(game_state, patch.time_label.strip())
        events.extend(check_imminent_deadlines(game_state, character))

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
                    f"- [{deadline.id}] {deadline.label}：已逾期 {format_duration(-remaining)}，"
                    "须在本轮或下轮裁定后果是否发生"
                )
            elif remaining == 0:
                lines.append(f"- [{deadline.id}] {deadline.label}：此刻到期")
            else:
                lines.append(
                    f"- [{deadline.id}] {deadline.label}：还剩 {format_duration(remaining)}"
                    f"（约 {narrative_time_display_at(game_state, deadline.due_at_minutes)}）"
                )
                if deadline.consequence.strip():
                    lines.append(f"  若未能阻止，可能后果：{deadline.consequence.strip()}")
                penalty_parts: list[str] = []
                if deadline.fail_quest_ids:
                    penalty_parts.append(f"可能失败任务 {', '.join(deadline.fail_quest_ids)}")
                if deadline.hp_loss > 0:
                    penalty_parts.append(f"可能伤害 {deadline.hp_loss}")
                if penalty_parts:
                    lines.append(f"  到期后若后果成立：{'；'.join(penalty_parts)}")

    due = [d for d in game_state.deadlines if _deadline_is_due(d)]
    if due:
        lines.append("已到期待裁定（须结合关键事实与本轮行动决定后果是否发生）：")
        for deadline in due:
            lines.append(f"- [{deadline.id}] {deadline.label}")
            if deadline.consequence.strip():
                lines.append(f"  若后果成立：{deadline.consequence.strip()}")

    resolved = [d for d in game_state.deadlines if d.status == "resolved"][-3:]
    if resolved:
        lines.append("近期已裁定时限：")
        for deadline in resolved:
            lines.append(f"- {deadline.label}")

    return "\n".join(lines)


def format_time_constraints_for_kp(game_state: GameState) -> str:
    pending = [d for d in game_state.deadlines if d.status == "pending"]
    due = [d for d in game_state.deadlines if _deadline_is_due(d)]
    overdue = [
        d for d in pending if _deadline_remaining(d, game_state.elapsed_minutes) < 0
    ]
    imminent = [
        d
        for d in pending
        if 0 <= _deadline_remaining(d, game_state.elapsed_minutes) <= _IMMINENT_MINUTES
    ]
    if not overdue and not imminent and not due:
        return ""

    lines = ["【时限约束 — 本轮叙事必须遵守】"]
    for deadline in due:
        lines.append(
            f"- 「{deadline.label}」已到期：须结合【关键事实】与玩家已采取的对策裁定后果是否发生。"
        )
        if deadline.consequence.strip():
            lines.append(f"  若未能阻止时的后果：{deadline.consequence.strip()}")
        lines.append(
            "  若玩家已提前化解（如远程改日志、拆弹、贿赂、伪装维护），写化解过程，"
            "勿写失败后果；若确实未能阻止，才写到期后果。"
        )
        lines.append("  任务成败不由系统自动判定，须与上述裁定一致。")
    for deadline in overdue:
        lines.append(
            f"- 「{deadline.label}」已过期：须在本轮裁定该事件是否发生，禁止假装尚未到期。"
        )
        if deadline.consequence.strip():
            lines.append(f"  若未能阻止时的后果：{deadline.consequence.strip()}")
    for deadline in imminent:
        remaining = _deadline_remaining(deadline, game_state.elapsed_minutes)
        lines.append(
            f"- 「{deadline.label}」仅剩 {format_duration(remaining)}：须体现紧迫，勿再拖延。"
        )
    lines.append(
        "禁止出现与【叙事时间】矛盾的表述（如已过去数小时却仍写「还有六小时才开始」）。"
    )
    return "\n".join(lines)


def format_player_stated_duration_hint(user_input: str) -> str:
    """供 State Agent 参考的玩家口头耗时声明（非权威，须 AI 裁定）。"""
    minutes = parse_stated_action_minutes(user_input)
    if minutes is None:
        return "（无）"
    return (
        f"玩家声称约 {minutes} 分钟；须结合角色背景、能力、技能、已有装备、"
        "世界观、场景条件与机械结算判断是否合理，不合理则按你的估算填写 advance_minutes"
    )


def resolve_turn_time(
    time_patch: TimePatch | None,
    *,
    route: ActionRouteResult | None,
    user_input: str,
    game_state: GameState,
    has_time_field: bool,
) -> tuple[int, str]:
    """决定本轮应推进的分钟数：玩家明确等待 > State Agent 的 advance_minutes。"""
    explicit = parse_explicit_wait_minutes(
        user_input,
        elapsed_minutes=game_state.elapsed_minutes,
        story_start_absolute=game_state.story_start_absolute_minutes,
    )
    if explicit is not None:
        return explicit, _explicit_wait_reason(user_input)

    if time_patch is not None and time_patch.advance_minutes > 0:
        reason = time_patch.advance_reason.strip() or "世界状态同步器裁定（未说明具体原因）"
        return time_patch.advance_minutes, reason

    if has_time_field and time_patch is not None:
        if time_patch.time_label or time_patch.deadlines or time_patch.cancel_deadline_ids or time_patch.enforce_deadline_ids:
            return 0, ""
        return 0, ""

    return 0, ""


def resolve_turn_advance_minutes(
    time_patch: TimePatch | None,
    *,
    route: ActionRouteResult | None,
    user_input: str,
    game_state: GameState,
    has_time_field: bool,
) -> int:
    """决定本轮应推进的分钟数：玩家明确等待 > State Agent 的 advance_minutes。"""
    minutes, _ = resolve_turn_time(
        time_patch,
        route=route,
        user_input=user_input,
        game_state=game_state,
        has_time_field=has_time_field,
    )
    return minutes


def apply_turn_time_from_patch(
    game_state: GameState,
    time_patch: TimePatch | None,
    *,
    route: ActionRouteResult | None,
    user_input: str,
    character: Character | None,
    has_time_field: bool,
    mechanical_events: list[str] | None = None,
    recent_history: str = "",
) -> list[str]:
    minutes, reason = resolve_turn_time(
        time_patch,
        route=route,
        user_input=user_input,
        game_state=game_state,
        has_time_field=has_time_field,
    )
    if time_patch is None and minutes <= 0:
        return _finalize_turn_time_events(game_state, character)

    patch = time_patch if time_patch is not None else TimePatch()
    if minutes > 0 and patch.advance_minutes <= 0:
        patch = patch.model_copy(update={"advance_minutes": minutes, "advance_reason": reason})
    elif minutes > 0 and patch.advance_minutes > 0 and not patch.advance_reason.strip():
        patch = patch.model_copy(update={"advance_reason": reason})
    elif minutes <= 0 and not (
        patch.time_label or patch.deadlines or patch.cancel_deadline_ids or patch.enforce_deadline_ids
    ):
        return _finalize_turn_time_events(game_state, character)

    blocked_events: list[str] = []
    if patch.deadlines:
        from game.deadline_grounding import build_deadline_corpus, filter_deadline_patches

        corpus = build_deadline_corpus(
            user_input=user_input,
            memory_facts=game_state.memory_facts,
            mechanical_events=mechanical_events,
            recent_history=recent_history,
        )
        filtered, blocked_events = filter_deadline_patches(patch.deadlines, corpus)
        patch = patch.model_copy(update={"deadlines": filtered})

    events = blocked_events + apply_time_patch(game_state, patch, character)
    return _finalize_turn_time_events(game_state, character, events)


def _finalize_turn_time_events(
    game_state: GameState,
    character: Character | None,
    base_events: list[str] | None = None,
) -> list[str]:
    from game.background_process import resolve_background_processes

    events = list(base_events or [])
    events.extend(check_imminent_deadlines(game_state, character=character))
    events.extend(resolve_background_processes(game_state))
    return events
