"""单回合流水线上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field

from game.models import Character, ChatMessage, GameState
from game.results import ActionRouteResult, StatePatch
from game.scenario import Scenario


@dataclass
class TurnContext:
    user_input: str
    character: Character
    game_state: GameState
    scenario: Scenario
    history: list[ChatMessage]
    windowed_history: list[ChatMessage] = field(default_factory=list)
    enriched_input: str = ""
    route: ActionRouteResult | None = None
    mechanical_events: list[str] = field(default_factory=list)
    world_patch: StatePatch = field(default_factory=StatePatch)
    item_patch: StatePatch = field(default_factory=StatePatch)
    narrative_brief: str = ""
    kp_response: str = ""
    world_state_events: list[str] = field(default_factory=list)
    item_sync_events: list[str] = field(default_factory=list)
    stat_forge_events: list[str] = field(default_factory=list)
    rejected: bool = False
    rejection_reason: str = ""
    increment_turn: bool = True
    is_opening: bool = False

    @property
    def effective_input(self) -> str:
        return self.enriched_input.strip() or self.user_input.strip()

    @property
    def all_state_events(self) -> list[str]:
        return self.world_state_events + self.item_sync_events + self.stat_forge_events

    @property
    def all_tool_events(self) -> list[str]:
        return self.mechanical_events + self.all_state_events
