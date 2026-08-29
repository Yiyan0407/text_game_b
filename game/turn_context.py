"""单回合流水线上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field

from game.game_config import GameConfig, default_game_config
from game.models import Character, ChatMessage, GameState
from game.results import ActionRouteResult, StatePatch
from game.scenario import Scenario
from game.settlement_plan import SettlementPlan


@dataclass
class TurnContext:
    user_input: str
    character: Character
    game_state: GameState
    scenario: Scenario
    history: list[ChatMessage]
    game_config: GameConfig = field(default_factory=default_game_config)
    windowed_history: list[ChatMessage] = field(default_factory=list)
    enriched_input: str = ""
    route: ActionRouteResult | None = None
    mechanical_events: list[str] = field(default_factory=list)
    post_kp_events: list[str] = field(default_factory=list)
    settlement_plan: SettlementPlan | None = None
    inventory_patch: StatePatch = field(default_factory=StatePatch)
    skill_patch: StatePatch = field(default_factory=StatePatch)
    time_patch: StatePatch = field(default_factory=StatePatch)
    world_patch: StatePatch = field(default_factory=StatePatch)
    narrative_brief: str = ""
    kp_response: str = ""
    inventory_sync_events: list[str] = field(default_factory=list)
    skill_sync_events: list[str] = field(default_factory=list)
    time_sync_events: list[str] = field(default_factory=list)
    world_sync_events: list[str] = field(default_factory=list)
    stat_forge_events: list[str] = field(default_factory=list)
    rejected: bool = False
    rejection_reason: str = ""
    increment_turn: bool = True
    is_opening: bool = False
    map_needs_update: bool = False
    map_travel_from: str = ""

    @property
    def effective_input(self) -> str:
        return self.enriched_input.strip() or self.user_input.strip()

    @property
    def settlement_events(self) -> list[str]:
        return self.mechanical_events + self.post_kp_events

    @property
    def all_state_events(self) -> list[str]:
        return (
            self.inventory_sync_events
            + self.skill_sync_events
            + self.time_sync_events
            + self.world_sync_events
            + self.stat_forge_events
        )

    @property
    def all_tool_events(self) -> list[str]:
        return self.settlement_events + self.all_state_events
