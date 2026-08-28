"""开场行动建议默认值。"""

from __future__ import annotations

from game.models import GameState
from game.scenario import Scenario


def default_opening_suggestions(scenario: Scenario, game_state: GameState) -> list[str]:
    scene = game_state.current_scene or scenario.opening_scene_name or "当前场景"
    if game_state.active_quests:
        quest = game_state.active_quests[0].title
        return [
            f"观察{scene}周围",
            f"着手：{quest}",
            "和在场的人交谈",
        ]
    return [
        f"观察{scene}周围",
        "检查随身物品",
        "和在场的人交谈",
    ]
