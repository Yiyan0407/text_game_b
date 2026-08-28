from typing import Literal

from pydantic import BaseModel, Field

from game.models import DiceRoll


class AbilityCheckResult(BaseModel):
    ability: str
    dc: int
    roll: DiceRoll
    proficiency_bonus: int = 0
    skill_bonus: int = 0
    situational_bonus: int = 0
    check_total: int = 0
    success: bool

    def describe(self) -> str:
        ability_label = self.ability.upper()
        outcome = "成功 ✓" if self.success else "失败 ✗"
        prof_part = f"+{self.proficiency_bonus}专业 " if self.proficiency_bonus else ""
        skill_part = f"+{self.skill_bonus}技能 " if self.skill_bonus else ""
        total = self.check_total if self.check_total else self.roll.total
        return (
            f"{ability_label} 检定 {self.roll.describe()} {prof_part}{skill_part}"
            f"= {total} vs DC {self.dc} → {outcome}"
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
        "move",
        "dash",
        "end_turn",
    ] = "none"
    action_cost: Literal["main", "bonus", "free"] = "main"
    attack_target: str = ""
    move_target: str = ""
    move_meters: int = 0
    move_toward: bool = True
    ends_turn: bool = False
    proficiency_bonus: bool = False
    enemy_defs: list["EnemyDefPatch"] = Field(default_factory=list)
    sync_inventory: bool = True


class EnemyDefPatch(BaseModel):
    name: str = ""
    hp: int = 0
    ac: int = 12
    attack_damage: str = "1d6"
    attack_bonus: int = 3
    sp: int = 0
    sp_max: int = 0
    start_distance_m: int = 10

    def to_combat_enemy(self) -> "CombatEnemy":
        from game.models import CombatEnemy

        hp = max(1, self.hp)
        sp = max(0, self.sp)
        sp_max = max(sp, self.sp_max) if self.sp_max > 0 else sp
        attack = (self.attack_damage or "1d6").strip()
        return CombatEnemy(
            name=self.name.strip(),
            hp=hp,
            max_hp=hp,
            ac=max(1, self.ac or 12),
            attack_bonus=self.attack_bonus,
            attack_damage=attack,
            damage_notation=attack,
            sp=sp,
            sp_max=sp_max,
            start_distance_m=max(0, self.start_distance_m or 10),
        )


class ScenePatch(BaseModel):
    scene_id: str = ""
    scene_name: str = ""


class NpcPatch(BaseModel):
    name: str = ""
    attitude: Literal["friendly", "neutral", "hostile", "unknown"] = "unknown"
    notes: str = ""


class QuestPatch(BaseModel):
    quest_id: str = ""
    title: str = ""
    status: Literal["active", "completed", "failed"] = "active"
    description: str = ""


class InventoryPatch(BaseModel):
    action: Literal["add", "remove"] = "add"
    item: str = ""
    quantity: int = 1
    unit: str = "个"
    description: str = ""
    kind: Literal["consumable", "durable", "document"] | None = None


class SkillPatch(BaseModel):
    action: Literal["add", "remove"] = "add"
    skill: str = ""
    description: str = ""


class EquipmentPatch(BaseModel):
    action: Literal["equip", "unequip"] = "equip"
    item: str = ""
    slot: str = ""


class DeadlinePatch(BaseModel):
    id: str = ""
    label: str = ""
    due_in_minutes: int = 0
    due_at_minutes: int | None = None
    consequence: str = ""
    status: Literal["pending", "cancelled"] = "pending"
    fail_quest_ids: list[str] = Field(default_factory=list)
    hp_loss: int = 0


class TimePatch(BaseModel):
    time_label: str = ""
    advance_minutes: int = 0
    advance_reason: str = ""
    deadlines: list[DeadlinePatch] = Field(default_factory=list)
    cancel_deadline_ids: list[str] = Field(default_factory=list)
    enforce_deadline_ids: list[str] = Field(default_factory=list)


class StatePatch(BaseModel):
    scene: ScenePatch | None = None
    npcs: list[NpcPatch] = Field(default_factory=list)
    quests: list[QuestPatch] = Field(default_factory=list)
    inventory: list[InventoryPatch] = Field(default_factory=list)
    equipment: list[EquipmentPatch] = Field(default_factory=list)
    skills: list[SkillPatch] = Field(default_factory=list)
    memory_facts: list[str] = Field(default_factory=list)
    time: TimePatch | None = None
    end_combat: bool = False


class StreamPhase(BaseModel):
    """流式回合的一个阶段输出。"""

    kind: Literal["mechanical", "state", "narrative", "done"] = "narrative"
    events: list[str] = Field(default_factory=list)
    chunk: str = ""


class TurnResult(BaseModel):
    response: str
    tool_events: list[str] = Field(default_factory=list)
    summary_updated: bool = False
    action_suggestions: list[str] = Field(default_factory=list)
    rejected: bool = False
    rejection_reason: str = ""
    opening_used_fallback: bool = False

    @property
    def has_tool_events(self) -> bool:
        return bool(self.tool_events)
