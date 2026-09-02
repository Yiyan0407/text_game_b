"""解析「继续/接着」等短输入在途旅行语境下的真实意图。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from game.kp_directive import is_kp_meta_response
from game.models import ChatMessage, GameState

_CONTINUATION_PHRASES = frozenset(
    {
        "继续",
        "接着",
        "然后呢",
        "往下",
        "下一步",
        "继续吧",
        "继续推进",
        "继续走",
        "继续开",
        "继续前往",
        "continue",
    }
)

_TRAVEL_VERBS = (
    "前往",
    "赶到",
    "抵达",
    "开到",
    "驶向",
    "行驶",
    "赶路",
    "出发去",
    "去",
)

_TRAVEL_GOALS = (
    "修车",
    "修理",
    "维修",
    "整备",
    "升级武器",
    "武器升级",
    "改装",
    "加油",
    "补给",
)

_ARRIVAL_MARKERS = (
    "抵达",
    "到达",
    "驶入",
    "开进",
    "停在",
    "下车",
    "走进",
    "进入",
    "到了",
)

_REMAINING_DISTANCE = re.compile(
    r"(?:还有|距|离|尚(?:差|有)?|约|大概|大约)\s*"
    r"(?:[\d一二三四五六七八九十两]+)\s*(?:分钟|分|公里|km|米|里|mile|miles)"
)

_REMAINING_TIME = re.compile(
    r"(?:还有|尚需|大约|大概|约)\s*"
    r"(?:[\d一二三四五六七八九十两]+)\s*(?:分钟|分|小时|钟头)"
)

_DESTINATION_PATTERNS = (
    re.compile(r"(?:前往|赶到|去往|开向|驶向|目的地[是为：:]\s*)(.{2,40})"),
    re.compile(r"([\u4e00-\u9fffA-Za-z0-9·\-—]{2,30}(?:废墟|修车棚|修车厂|旅馆|营地|据点|入口|站))"),
    re.compile(r"(汽车旅馆[^，。；\n]{0,20}修车棚?)"),
    re.compile(r"(收费站[^，。；\n]{0,20})"),
)


@dataclass(frozen=True)
class TravelContinuation:
    """在途旅行续行解析结果。"""

    destination: str
    resolved_intent: str
    must_arrive: bool
    reason: str


def _normalize_input(text: str) -> str:
    return (text or "").strip().casefold()


def is_continuation_input(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    folded = _normalize_input(text)
    if folded in _CONTINUATION_PHRASES:
        return True
    if len(text) <= 8 and any(folded.startswith(p) for p in _CONTINUATION_PHRASES):
        return True
    return False


def _recent_user_messages(history: list[ChatMessage], *, limit: int = 5) -> list[str]:
    messages: list[str] = []
    for msg in reversed(history):
        if msg.role != "user":
            continue
        content = msg.content.strip()
        if content:
            messages.append(content)
        if len(messages) >= limit:
            break
    return list(reversed(messages))


def _last_kp_text(history: list[ChatMessage]) -> str:
    for msg in reversed(history):
        if msg.role != "assistant":
            continue
        if is_kp_meta_response(msg.content):
            continue
        return msg.content.strip()
    return ""


def _corpus(*parts: str) -> str:
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _has_travel_goal(text: str) -> bool:
    return any(marker in text for marker in _TRAVEL_GOALS) or any(
        verb in text for verb in _TRAVEL_VERBS
    )


def _extract_destination(*parts: str) -> str:
    corpus = _corpus(*parts)
    for pattern in _DESTINATION_PATTERNS:
        match = pattern.search(corpus)
        if not match:
            continue
        candidate = match.group(1).strip(" 。，；：:\"'「」")
        if len(candidate) >= 2:
            return candidate[:48]
    if "修车棚" in corpus:
        if "汽车旅馆" in corpus:
            return "汽车旅馆修车棚"
        return "修车棚"
    if "收费站" in corpus and "废墟" in corpus:
        return "收费站废墟"
    if "收费站" in corpus:
        return "收费站"
    return ""


def _travel_time_already_spent(state_events: list[str] | None) -> bool:
    """上一回合机械层是否已按「前往/行驶」推进过较长时间。"""
    for event in state_events or []:
        if "时间推进" not in event and "时间]" not in event:
            continue
        if any(verb in event for verb in ("前往", "行驶", "驾驶", "赶路", "开向", "驶向")):
            return True
        if re.search(r"\+?\s*\d+\s*分", event) and any(
            verb in event for verb in _TRAVEL_VERBS
        ):
            return True
    return False


def _kp_mid_travel(kp_text: str) -> bool:
    if not kp_text:
        return False
    if _REMAINING_DISTANCE.search(kp_text) or _REMAINING_TIME.search(kp_text):
        if not any(marker in kp_text for marker in _ARRIVAL_MARKERS):
            return True
    driving_markers = ("继续往", "往西北", "往东北", "往前开", "沿公路", "还在路上", "尚未到达")
    if any(marker in kp_text for marker in driving_markers):
        if not any(marker in kp_text for marker in _ARRIVAL_MARKERS):
            return True
    return False


def resolve_travel_continuation(
    user_input: str,
    *,
    history: list[ChatMessage] | None = None,
    game_state: GameState | None = None,
    state_events: list[str] | None = None,
) -> TravelContinuation | None:
    """若玩家短句「继续」是在途旅行语境，解析为须抵达的目的地。"""
    if not is_continuation_input(user_input):
        return None

    history = history or []
    recent_users = _recent_user_messages(history)
    last_kp = _last_kp_text(history)
    memory_facts = "\n".join((game_state.memory_facts if game_state else [])[-8:])
    user_corpus = _corpus(*recent_users)
    full_corpus = _corpus(user_corpus, last_kp, memory_facts)

    if not _has_travel_goal(user_corpus) and not _kp_mid_travel(last_kp):
        if not any(goal in full_corpus for goal in _TRAVEL_GOALS):
            return None
        if not any(verb in full_corpus for verb in _TRAVEL_VERBS):
            return None

    destination = _extract_destination(memory_facts, last_kp, user_corpus)
    if not destination:
        if _kp_mid_travel(last_kp):
            destination = "先前对话中提及的目的地"
        else:
            return None

    must_arrive = _kp_mid_travel(last_kp) or bool(
        _REMAINING_DISTANCE.search(last_kp) or _REMAINING_TIME.search(last_kp)
    )
    if not must_arrive and _has_travel_goal(user_corpus):
        must_arrive = True
    if not must_arrive and _travel_time_already_spent(state_events):
        must_arrive = True

    goal_bits = [bit for bit in _TRAVEL_GOALS if bit in user_corpus]
    goal_hint = "、".join(goal_bits[:2]) if goal_bits else "完成行程"

    if must_arrive:
        resolved = f"继续前往「{destination}」并本回合抵达，以便{goal_hint}"
        reason = "上一轮叙事仍在途中或尚有余程，玩家输入「继续」意为推进至目的地而非半途新增变故"
    else:
        resolved = f"继续前往「{destination}」，推进{goal_hint}"
        reason = "近期玩家表达了移动/整备目标，短句「继续」应沿该目标推进"

    return TravelContinuation(
        destination=destination,
        resolved_intent=resolved,
        must_arrive=must_arrive,
        reason=reason,
    )


def format_travel_continuation_for_kp(continuation: TravelContinuation) -> str:
    lines = [
        "【在途旅行 — 叙事硬约束】",
        f"- 玩家本句「继续」的系统解析：{continuation.resolved_intent}",
        f"- 依据：{continuation.reason}",
    ]
    if continuation.must_arrive:
        lines.extend(
            [
                f"- **本回合须写抵达「{continuation.destination}」**（或刚驶入/刚停下的瞬间）。",
                "- 可以在此遭遇抛锚、威胁等变故，但**不可**再写「尚差数公里/尚未到达/还在半路」。",
                "- 若【叙事时间】上一回合已消耗接近 ETA 的路程时间，本回合应完成抵达并同步换场。",
            ]
        )
    else:
        lines.append(
            f"- 沿前往「{continuation.destination}」推进；若本回合应到达，须明确写抵达而非无限拖延。"
        )
    return "\n".join(lines)
