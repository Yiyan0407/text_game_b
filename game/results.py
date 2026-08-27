from typing import Literal

from pydantic import BaseModel, Field

from game.models import DiceRoll


class AbilityCheckResult(BaseModel):
    ability: str
    dc: int
    roll: DiceRoll
    success: bool

    def describe(self) -> str:
        ability_label = self.ability.upper()
        outcome = "成功 ✓" if self.success else "失败 ✗"
        return (
            f"{ability_label} 检定 {self.roll.describe()} "
            f"vs DC {self.dc} → {outcome}"
        )


class ActionRouteResult(BaseModel):
    approved: bool = False
    rejection_reason: str = ""
    needs_roll: bool = False
    roll_type: Literal["ability_check", "dice", "none"] = "none"
    ability: str = ""
    dc: int = 0
    dice_notation: str = ""
    referenced_items: list[str] = Field(default_factory=list)
    referenced_skills: list[str] = Field(default_factory=list)
    payment_items: list[str] = Field(default_factory=list)
    payment_quantity: int = 1
    item_usage: Literal["none", "use", "pickup", "observe", "purchase"] = "none"
    skill_usage: Literal["none", "use", "learn"] = "none"
    action_intent: str = ""
    scope_stop: str = ""
    must_not_narrate: list[str] = Field(default_factory=list)
    mode: Literal["exploration", "combat"] = "exploration"
    trigger_combat: bool = False
    enemies_spec: str = ""
    combat_action: Literal[
        "none",
        "attack",
        "flee",
        "defend",
        "use_item",
        "interact",
        "talk",
        "grapple",
        "shove",
        "help",
        "search",
        "end_turn",
    ] = "none"
    action_cost: Literal["main", "bonus", "free"] = "main"
    attack_target: str = ""
    ends_turn: bool = False


class TurnResult(BaseModel):
    response: str
    tool_events: list[str] = Field(default_factory=list)
    summary_updated: bool = False
    action_suggestions: list[str] = Field(default_factory=list)
    rejected: bool = False
    rejection_reason: str = ""

    @property
    def has_tool_events(self) -> bool:
        return bool(self.tool_events)
