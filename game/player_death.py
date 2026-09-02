"""玩家死亡（HP 0）判定与提示。"""

from __future__ import annotations

import re

from game.models import Character

DEATH_EVENT = "💀 你已死亡（HP 0）。"
DEATH_REJECTION = "角色已死亡（HP 0），无法执行该行动。请使用【kp】沟通，或从主菜单读取其他存档。"

_DEATH_MECHANICAL_MARKERS = (
    DEATH_EVENT,
    "你已死亡",
    "HP 0/",
    "[自动战斗] 战斗结束：你已死亡",
)

_RESPAWN_MEMORY_RE = re.compile(
    r"重生|复活|循环.{0,4}重生|满血|再次睁开眼|身体完全恢复|装备重置|对手也会复活"
)


def player_death_confirmed(
    character: Character | None,
    mechanical_events: list[str] | None = None,
) -> bool:
    if character is not None and not character.is_alive():
        return True
    for event in mechanical_events or []:
        if any(marker in event for marker in _DEATH_MECHANICAL_MARKERS):
            return True
    return False


def format_death_constraints_for_kp(
    character: Character | None,
    mechanical_events: list[str] | None = None,
) -> str:
    if not player_death_confirmed(character, mechanical_events):
        return ""
    return "\n".join(
        [
            "【死亡结局 — 叙事硬约束】",
            "- 机械层已确认玩家 **永久死亡**（HP 0）；须写死亡过程与余波/尾声。",
            "- **禁止**写：重生、复活、满血醒来、循环竞技场、场景重置式「再来一遍」、",
            "  时间倒流、对手全体复活、装备/伤势自动恢复、继续冒险的新开场。",
            "- 可写：失去意识、最后一幕、他人反应、任务失败后果、世界如何继续（不含玩家行动）。",
            "- 除非玩家用【kp】meta 指令明确要求测试/改 HP，否则死亡不可逆。",
        ]
    )


def is_respawn_memory_text(text: str) -> bool:
    return bool(_RESPAWN_MEMORY_RE.search(text.strip()))


def death_events_if_needed(character: Character) -> list[str]:
    if character.is_alive():
        return []
    return [DEATH_EVENT]
