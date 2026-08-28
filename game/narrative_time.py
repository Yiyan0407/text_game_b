"""叙事时间轴：故事内时钟、行动耗时估算与时限触发。"""

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
_INJURY_KEYWORDS = ("受伤", "爆炸", "伤害", "灼烧", "中毒", "失血", "遇袭", "遇险")


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


def infer_opening_time_label(scenario: Scenario) -> str:
    text = " ".join(
        part
        for part in (
            scenario.opening_prompt,
            scenario.opening_scene_name,
            scenario.tone,
            scenario.description,
        )
        if part
    )
    rules: list[tuple[tuple[str, ...], tuple[int, int, int]]] = [
        (("凌晨", "拂晓", "黎明", "清晨", "天亮"), (1, 5, 30)),
        (("上午", "早晨", "早间"), (1, 9, 0)),
        (("正午", "中午"), (1, 12, 0)),
        (("下午", "午后"), (1, 15, 0)),
        (("黄昏", "日落", "傍晚"), (1, 18, 30)),
        (("夜班", "值夜"), (1, 23, 0)),
        (("深夜",), (1, 23, 30)),
        (("午夜", "子夜"), (1, 0, 0)),
        (("夜晚", "晚上", "夜间", "夜里", "雨夜", "月夜"), (1, 21, 0)),
    ]
    for keywords, (day, hour, minute) in rules:
        if any(keyword in text for keyword in keywords):
            return format_clock(0, absolute_minutes_from_day_time(day, hour, minute))
    return format_clock(0, _DEFAULT_START_MINUTE)


def apply_story_clock_label(game_state: GameState, label: str) -> None:
    parsed = parse_time_label(label)
    if parsed is None:
        game_state.narrative_time_label = label.strip()
        return

    day, hour, minute = parsed
    absolute = absolute_minutes_from_day_time(day, hour, minute)
    if game_state.turn_count == 0 and game_state.elapsed_minutes == 0:
        game_state.story_start_absolute_minutes = absolute
        game_state.elapsed_minutes = 0
    else:
        game_state.elapsed_minutes = max(
            0, absolute - game_state.story_start_absolute_minutes
        )
    game_state.narrative_time_label = format_clock(
        game_state.elapsed_minutes,
        game_state.story_start_absolute_minutes,
    )


def initialize_story_clock_from_scenario(game_state: GameState, scenario: Scenario) -> None:
    if game_state.elapsed_minutes != 0:
        return
    if parse_time_label(game_state.narrative_time_label):
        return
    apply_story_clock_label(game_state, infer_opening_time_label(scenario))


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


def estimate_turn_time(
    route: ActionRouteResult | None,
    user_input: str,
    game_state: GameState,
) -> tuple[int, str]:
    explicit = parse_explicit_wait_minutes(
        user_input,
        elapsed_minutes=game_state.elapsed_minutes,
        story_start_absolute=game_state.story_start_absolute_minutes,
    )
    if explicit is not None:
        return explicit, _explicit_wait_reason(user_input)

    text = user_input.strip()
    intent = route.action_intent.strip() if route else ""
    combined = f"{intent} {text}"

    if game_state.is_in_combat():
        return 6, "战斗中进行了一轮行动（系统估算）"

    if route and route.trigger_combat:
        return 5, "触发战斗，进入交战（系统估算）"

    long_wait_markers = ("整晚", "半天", "一整天", "一天", "数日")
    if any(marker in combined for marker in long_wait_markers):
        if "半天" in combined:
            return 12 * 60, "长时间等待：约半天（系统估算）"
        if "一天" in combined or "整日" in combined:
            return _STORY_DAY_MINUTES, "长时间等待：约一整天（系统估算）"
        if "数日" in combined:
            return 2 * _STORY_DAY_MINUTES, "长时间等待：约数日（系统估算）"

    travel_markers = ("长途", "跨城", "赶到", "前往", "驱车", "飞行", "坐火车", "转场")
    if any(marker in combined for marker in travel_markers):
        return 45, "跨场景移动/赶路（系统估算）"

    scene_markers = ("进入", "离开", "返回", "赶到", "抵达")
    if any(marker in combined for marker in scene_markers):
        return 25, "场景切换与就位（系统估算）"

    search_markers = ("搜查", "搜证", "排查", "全面调查", "翻找")
    if any(marker in combined for marker in search_markers):
        return 30, "搜查/调查耗时（系统估算）"

    negotiation_markers = ("谈判", "交涉", "讨价还价", "商量条件")
    if any(marker in combined for marker in negotiation_markers):
        return 10, "谈判/交涉（系统估算）"

    talk_markers = ("交谈", "对话", "询问", "闲聊", "搭话", "追问", "质疑", "盘问")
    question_markers = (
        "?", "？", "谁", "什么", "啥", "怎么", "如何", "为何", "为什么",
        "哪", "吗", "么", "是不是", "多少", "几点", "干嘛", "干什么",
    )
    if any(marker in combined for marker in talk_markers) or any(
        marker in text for marker in question_markers
    ):
        return 2, "简短对话/问答（系统估算）"

    quick_markers = ("观察", "查看", "检查", "倾听", "偷听", "阅读", "点头", "沉默")
    if any(marker in combined for marker in quick_markers):
        return 3, "快速观察/检查（系统估算）"

    if route and route.item_usage == "purchase":
        return 12, "购买与交割（系统估算）"

    if route and route.combat_action == "talk":
        return 3, "战斗中简短喊话（系统估算）"

    return 4, "常规行动（系统估算）"


def estimate_turn_minutes(
    route: ActionRouteResult | None,
    user_input: str,
    game_state: GameState,
) -> int:
    minutes, _ = estimate_turn_time(route, user_input, game_state)
    return minutes


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
    target_id = deadline_id.strip()
    if not target_id:
        return None
    for deadline in game_state.deadlines:
        if deadline.id == target_id and deadline.status == "pending":
            deadline.status = "cancelled"
            return f"⏰ 已取消时限：{deadline.label}"
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


def _default_hp_loss(consequence: str, configured: int) -> int:
    if configured > 0:
        return configured
    if any(keyword in consequence for keyword in _INJURY_KEYWORDS):
        return 5
    return 0


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

    hp_loss = _default_hp_loss(deadline.consequence, deadline.hp_loss)
    if character is not None and hp_loss > 0:
        before = character.hp
        character.hp = max(1, character.hp - hp_loss)
        actual = before - character.hp
        if actual > 0:
            events.append(f"💔 时限后果：受到 {actual} 点伤害（HP {character.hp}/{character.max_hp}）")

    return events


def _trigger_deadline(
    game_state: GameState,
    deadline: NarrativeDeadline,
    character: Character | None = None,
) -> list[str]:
    from config.settings import get_settings

    deadline.status = "triggered"
    overdue = format_duration(max(0, game_state.elapsed_minutes - deadline.due_at_minutes))
    events = [f"⏰ 时限已到：{deadline.label}（逾期 {overdue}）"]
    fact = f"时限「{deadline.label}」已到期"
    if deadline.consequence.strip():
        fact = f"{fact}；后果：{deadline.consequence.strip()}"
    game_state.add_memory_facts([fact], get_settings().max_memory_facts)
    events.extend(_apply_deadline_penalties(game_state, deadline, character))
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
                    "系统已执行失败/伤害等惩罚，本轮必须体现后果"
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
                penalty_parts: list[str] = []
                if deadline.fail_quest_ids:
                    penalty_parts.append(f"失败任务 {', '.join(deadline.fail_quest_ids)}")
                if deadline.hp_loss > 0:
                    penalty_parts.append(f"伤害 {deadline.hp_loss}")
                elif any(keyword in deadline.consequence for keyword in _INJURY_KEYWORDS):
                    penalty_parts.append("伤害（默认 5）")
                if penalty_parts:
                    lines.append(f"  到期惩罚：{'；'.join(penalty_parts)}")

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
        lines.append("  系统已执行相关任务失败/伤害惩罚，叙事须与之吻合。")
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
    """决定本轮应推进的分钟数及原因：显式等待 > State Agent 裁定 > 启发式兜底。"""
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
        if time_patch.time_label or time_patch.deadlines or time_patch.cancel_deadline_ids:
            return 0, ""
        return 0, ""

    return estimate_turn_time(route, user_input, game_state)


def resolve_turn_advance_minutes(
    time_patch: TimePatch | None,
    *,
    route: ActionRouteResult | None,
    user_input: str,
    game_state: GameState,
    has_time_field: bool,
) -> int:
    """决定本轮应推进的分钟数：显式等待 > State Agent 裁定 > 启发式兜底。"""
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
) -> list[str]:
    minutes, reason = resolve_turn_time(
        time_patch,
        route=route,
        user_input=user_input,
        game_state=game_state,
        has_time_field=has_time_field,
    )
    if time_patch is None and minutes <= 0:
        return []

    patch = time_patch if time_patch is not None else TimePatch()
    if minutes > 0 and patch.advance_minutes <= 0:
        patch = patch.model_copy(update={"advance_minutes": minutes, "advance_reason": reason})
    elif minutes > 0 and patch.advance_minutes > 0 and not patch.advance_reason.strip():
        patch = patch.model_copy(update={"advance_reason": reason})
    elif minutes <= 0 and not (
        patch.time_label or patch.deadlines or patch.cancel_deadline_ids
    ):
        return []

    return apply_time_patch(game_state, patch, character)


def advance_narrative_time_for_turn(
    route: ActionRouteResult | None,
    user_input: str,
    game_state: GameState,
    character: Character | None = None,
) -> list[str]:
    minutes, reason = estimate_turn_time(route, user_input, game_state)
    return advance_narrative_clock(game_state, minutes, character, reason=reason)
