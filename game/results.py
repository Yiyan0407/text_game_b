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


class TurnResult(BaseModel):
    response: str
    tool_events: list[str] = Field(default_factory=list)
    summary_updated: bool = False
    action_suggestions: list[str] = Field(default_factory=list)

    @property
    def has_tool_events(self) -> bool:
        return bool(self.tool_events)
