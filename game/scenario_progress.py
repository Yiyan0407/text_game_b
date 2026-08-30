"""剧本 key_node 进度追踪与 KP 注入。"""

from __future__ import annotations

import re

from game.game_config import KpGuidance
from game.models import GameState, ScenarioProgress
from game.scenario import Scenario, ScenarioNode

_BEAT_STOPWORDS = frozenset(
    {
        "一个",
        "一种",
        "可以",
        "进行",
        "玩家",
        "需要",
        "如果",
        "或者",
        "以及",
        "通过",
        "开始",
        "继续",
        "完成",
        "任务",
        "选择",
        "可能",
        "已经",
        "他们",
        "你们",
        "我们",
        "这个",
        "那个",
        "什么",
        "如何",
        "是否",
        "必须",
        "应当",
        "应该",
        "将会",
        "正在",
    }
)

SCRIPT_OVERDUE_TURNS = 4
BALANCED_OVERDUE_TURNS = 8


def initialize_scenario_progress(game_state: GameState) -> ScenarioProgress:
    game_state.scenario_progress = ScenarioProgress()
    return game_state.scenario_progress


def ensure_scenario_progress(game_state: GameState) -> ScenarioProgress:
    progress = game_state.scenario_progress
    if progress is None:
        return initialize_scenario_progress(game_state)
    return progress


def beat_key(node_id: str, index: int) -> str:
    return f"{node_id.strip()}:{index}"


def node_beats(node: ScenarioNode) -> list[str]:
    beats = [text.strip() for text in node.beats if text.strip()]
    if beats:
        return beats
    if node.description.strip():
        return [node.description.strip()]
    return []


def get_active_node(scenario: Scenario, progress: ScenarioProgress) -> ScenarioNode | None:
    if not scenario.key_nodes:
        return None
    index = max(0, min(progress.active_node_index, len(scenario.key_nodes) - 1))
    return scenario.key_nodes[index]


def pending_beat_items(
    scenario: Scenario,
    progress: ScenarioProgress,
) -> list[tuple[str, str]]:
    node = get_active_node(scenario, progress)
    if node is None:
        return []
    items: list[tuple[str, str]] = []
    for index, beat in enumerate(node_beats(node)):
        key = beat_key(node.id, index)
        if key not in progress.completed_beat_keys:
            items.append((key, beat))
    return items


def pending_beats(scenario: Scenario, progress: ScenarioProgress) -> list[str]:
    return [beat for _, beat in pending_beat_items(scenario, progress)]


def is_node_overdue(
    progress: ScenarioProgress,
    kp_guidance: KpGuidance,
    *,
    turn_count: int,
    has_pending: bool,
) -> bool:
    if not has_pending or kp_guidance == "freeform":
        return False
    threshold = (
        SCRIPT_OVERDUE_TURNS
        if kp_guidance == "script_guided"
        else BALANCED_OVERDUE_TURNS
    )
    if progress.last_beat_completed_turn > 0:
        return turn_count - progress.last_beat_completed_turn >= threshold
    return progress.turns_on_active_node >= threshold


def _beat_keywords(beat_text: str) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str) -> None:
        cleaned = value.strip()
        if len(cleaned) < 2 or cleaned in _BEAT_STOPWORDS:
            return
        folded = cleaned.casefold()
        if folded in seen:
            return
        seen.add(folded)
        keywords.append(cleaned)

    for match in re.finditer(r"[\u4e00-\u9fff]+|[A-Za-z]{3,}|\d{2,}", beat_text):
        token = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) <= 4:
                add_candidate(token)
            else:
                add_candidate(token[:4])
                add_candidate(token[-4:])
                for index in range(0, len(token) - 1, 2):
                    add_candidate(token[index : index + 2])
            continue
        add_candidate(token)
    return keywords


def beat_matches_corpus(beat_text: str, corpus: str) -> bool:
    keywords = _beat_keywords(beat_text)
    if not keywords:
        return False
    folded = corpus.casefold()
    hits = [keyword for keyword in keywords if keyword.casefold() in folded]
    if any(len(keyword) >= 4 for keyword in hits):
        return True
    return len(hits) >= 2


def _turn_corpus(
    kp_text: str,
    state_events: list[str],
    game_state: GameState,
) -> str:
    parts = [kp_text, "\n".join(state_events)]
    for npc in game_state.npcs:
        parts.append(npc.name)
        parts.append(npc.notes)
    for fact in game_state.memory_facts[-12:]:
        parts.append(fact)
    parts.append(game_state.current_scene)
    return "\n".join(part for part in parts if part)


def detect_completed_beats(
    kp_text: str,
    state_events: list[str],
    game_state: GameState,
    scenario: Scenario,
    progress: ScenarioProgress,
) -> list[str]:
    corpus = _turn_corpus(kp_text, state_events, game_state)
    newly_completed: list[str] = []
    for key, beat in pending_beat_items(scenario, progress):
        if beat_matches_corpus(beat, corpus):
            newly_completed.append(key)
    return newly_completed


def mark_beats_complete(
    progress: ScenarioProgress,
    beat_keys: list[str],
    *,
    turn_count: int,
) -> bool:
    added = False
    for key in beat_keys:
        if key in progress.completed_beat_keys:
            continue
        progress.completed_beat_keys.append(key)
        progress.last_beat_completed_turn = turn_count
        added = True
    return added


def advance_if_node_complete(scenario: Scenario, progress: ScenarioProgress) -> bool:
    node = get_active_node(scenario, progress)
    if node is None:
        return False
    beats = node_beats(node)
    if not beats:
        return False
    if len(pending_beat_items(scenario, progress)) > 0:
        return False
    if node.id not in progress.completed_node_ids:
        progress.completed_node_ids.append(node.id)
    if progress.active_node_index + 1 >= len(scenario.key_nodes):
        return True
    progress.active_node_index += 1
    progress.turns_on_active_node = 0
    progress.last_beat_completed_turn = 0
    return True


def tick_progress(progress: ScenarioProgress, *, beat_completed: bool) -> None:
    progress.turns_on_active_node += 1
    if beat_completed:
        progress.last_beat_completed_turn = progress.turns_on_active_node


def format_progress_for_kp(
    scenario: Scenario,
    progress: ScenarioProgress,
    kp_guidance: KpGuidance,
    *,
    turn_count: int = 0,
) -> str:
    if kp_guidance == "freeform":
        if turn_count > 1 or not scenario.key_nodes:
            return ""
        active = get_active_node(scenario, progress)
        if active is None:
            return ""
        return (
            "【剧本进度】\n"
            f"- 当前任务节点：{active.title}\n"
            "- 本局为自由即兴，节点仅作背景参考。"
        )

    node = get_active_node(scenario, progress)
    if node is None:
        return ""

    total = len(scenario.key_nodes)
    index = min(progress.active_node_index + 1, total)
    lines = [
        "【剧本进度】",
        f"- 当前节点：{index}/{total} · {node.title}",
    ]
    if node.description.strip():
        summary = node.description.strip()
        if len(summary) > 180:
            summary = summary[:177] + "…"
        lines.append(f"- 节点概要：{summary}")

    pending = pending_beats(scenario, progress)
    if pending:
        lines.append("- 待完成要素：")
        limit = len(pending) if kp_guidance == "script_guided" else 1
        for beat in pending[:limit]:
            lines.append(f"  · {beat}")
        if kp_guidance == "balanced" and len(pending) > 1:
            lines.append(f"  · （另有 {len(pending) - 1} 条待完成要素）")
    else:
        lines.append("- 待完成要素：（本节点已完成，可自然过渡至下一节点）")

    next_index = progress.active_node_index + 1
    if next_index < len(scenario.key_nodes):
        nxt = scenario.key_nodes[next_index]
        lines.append(f"- 下一节点预告：{nxt.title}")

    overdue = is_node_overdue(
        progress,
        kp_guidance,
        turn_count=turn_count,
        has_pending=bool(pending),
    )
    if overdue and pending:
        if kp_guidance == "script_guided":
            lines.append(
                "- **本回合须引入**：以上至少 1 条待完成要素须通过环境事件、"
                "通讯、NPC 接触等方式进入叙事（不可替玩家决定行动）。"
            )
        else:
            lines.append(
                "- 进展偏慢：可用 1–2 句环境细节或 NPC 台词铺垫上述待完成要素，勿抢戏。"
            )

    return "\n".join(lines)


def format_progress_for_ui(
    scenario: Scenario,
    progress: ScenarioProgress,
) -> tuple[str, list[str], int, int]:
    node = get_active_node(scenario, progress)
    if node is None:
        return "", [], 0, 0
    total = len(scenario.key_nodes)
    index = min(progress.active_node_index + 1, total)
    label = f"{index}/{total} · {node.title}"
    return label, pending_beats(scenario, progress), index, total


def update_scenario_progress_after_turn(
    game_state: GameState,
    scenario: Scenario,
    *,
    kp_text: str,
    state_events: list[str],
) -> list[str]:
    if not scenario.key_nodes:
        return []
    progress = ensure_scenario_progress(game_state)
    newly = detect_completed_beats(kp_text, state_events, game_state, scenario, progress)
    events: list[str] = []
    beat_completed = mark_beats_complete(
        progress,
        newly,
        turn_count=game_state.turn_count,
    )
    for key in newly:
        events.append(f"剧本进度：已完成要素 {key}")
    if advance_if_node_complete(scenario, progress):
        node = get_active_node(scenario, progress)
        if node is not None:
            events.append(f"剧本进度：进入节点 {node.title}")
        else:
            events.append("剧本进度：全部关键节点已完成")
    tick_progress(progress, beat_completed=beat_completed)
    return events
