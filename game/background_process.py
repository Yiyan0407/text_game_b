"""叙事后台进程：下载、更新、静默任务等，随故事时钟自动完成。"""

from __future__ import annotations

import re

from config.settings import get_settings
from game.models import BackgroundProcess, GameState
from game.results import BackgroundProcessPatch

_RUNNING_UPDATE_RE = re.compile(
    r"(?P<label>.{2,40}?)(?:正在|开始).{0,8}(?:更新|下载|安装|同步)"
)
_DURATION_RE = re.compile(
    r"预计(?:用时|还需)?\s*(?P<count>\d+)\s*(?P<unit>分钟|分|min|小时|h)",
    re.IGNORECASE,
)
_VERSION_RE = re.compile(r"\s*v?\d+(?:\.\d+)*", re.IGNORECASE)


def _normalize_process_key(label: str) -> str:
    return _VERSION_RE.sub("", label.strip()).casefold()


def _process_already_completed(game_state: GameState, label: str) -> bool:
    key = _normalize_process_key(label).replace(" ", "")
    if not key:
        return False
    for process in game_state.background_processes:
        if process.status == "completed" and _normalize_process_key(process.label).replace(" ", "") == key:
            return True
    for fact in game_state.memory_facts:
        if "已完成" not in fact:
            continue
        if key in _normalize_process_key(fact).replace(" ", ""):
            return True
    return False


def _ensure_process_id(label: str, proposed: str, existing_ids: set[str]) -> str:
    cleaned = proposed.strip()
    if cleaned and cleaned not in existing_ids:
        return cleaned
    slug = re.sub(r"\s+", "_", label.strip())[:24] or "process"
    candidate = slug
    index = 2
    while candidate in existing_ids:
        candidate = f"{slug}_{index}"
        index += 1
    return candidate


def _duration_to_minutes(count: int, unit: str) -> int:
    normalized = unit.strip().lower()
    if normalized in {"小时", "h"}:
        return max(1, count * 60)
    return max(1, count)


def register_background_process(
    game_state: GameState,
    patch: BackgroundProcessPatch,
) -> list[str]:
    label = patch.label.strip()
    if not label:
        return []
    if _process_already_completed(game_state, label):
        return []

    process_key = _normalize_process_key(label)
    for process in game_state.background_processes:
        if process.status == "running" and _normalize_process_key(process.label) == process_key:
            return []

    existing_ids = {item.id for item in game_state.background_processes}
    process_id = _ensure_process_id(label, patch.id, existing_ids)
    duration = max(1, int(patch.duration_minutes or 1))
    started_at = game_state.elapsed_minutes
    game_state.background_processes.append(
        BackgroundProcess(
            id=process_id,
            label=label,
            started_at_minutes=started_at,
            duration_minutes=duration,
            status="running",
            result_fact=patch.result_fact.strip(),
            blocks_actions=patch.blocks_actions.strip(),
        )
    )
    return [
        f"⏳ 后台启动：{label}（预计 {duration} 分，约 {format_clock_day(started_at + duration, game_state)} 完成）"
    ]


def resolve_background_processes(game_state: GameState) -> list[str]:
    events: list[str] = []
    settings = get_settings()
    for process in game_state.background_processes:
        if process.status != "running":
            continue
        due_at = process.started_at_minutes + process.duration_minutes
        if game_state.elapsed_minutes < due_at:
            continue
        process.status = "completed"
        fact = process.result_fact.strip() or f"{process.label}已完成"
        game_state.add_memory_facts([fact], settings.max_memory_facts)
        events.append(f"✅ 后台完成：{process.label}")
    return events


def format_background_processes_for_kp(game_state: GameState) -> str:
    running = [item for item in game_state.background_processes if item.status == "running"]
    if not running:
        completed = [item for item in game_state.background_processes if item.status == "completed"]
        if not completed:
            return ""
        recent = completed[-3:]
        lines = ["【后台进程 — 已完成，叙事勿写仍在下载/进度条】"]
        for process in recent:
            lines.append(f"- {process.label}：已完成")
        return "\n".join(lines)

    lines = ["【后台进程 — 须与故事时钟一致，禁止矛盾进度】"]
    for process in running:
        due_at = process.started_at_minutes + process.duration_minutes
        remaining = due_at - game_state.elapsed_minutes
        if remaining <= 0:
            lines.append(
                f"- {process.label}：按故事时间应已完成（勿写进度条/不可用/仍在下载）"
            )
        else:
            lines.append(
                f"- {process.label}：还剩约 {remaining} 分"
                + (f"；完成前{process.blocks_actions}不可用" if process.blocks_actions else "")
            )
    return "\n".join(lines)


def format_clock_day(absolute_minutes: int, game_state: GameState) -> str:
    from game.narrative_time import format_clock

    return format_clock(absolute_minutes, game_state.story_start_absolute_minutes)
