from typing import Literal, Self, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from game.memory_journal import normalize_topic
from game.models import DiceRoll


class AbilityCheckResult(BaseModel):
    ability: str
    dc: int
    roll: DiceRoll
    proficiency_bonus: int = 0
    skill_bonus: int = 0
    active_skill_bonus: int = 0
    passive_skill_bonus: int = 0
    passive_skills_applied: list[str] = Field(default_factory=list)
    situational_bonus: int = 0
    check_total: int = 0
    success: bool

    def describe(self) -> str:
        ability_label = self.ability.upper()
        outcome = "成功 ✓" if self.success else "失败 ✗"
        prof_part = f"+{self.proficiency_bonus}专业 " if self.proficiency_bonus else ""
        skill_part = ""
        if self.active_skill_bonus:
            skill_part += f"+{self.active_skill_bonus}主动 "
        if self.passive_skill_bonus != 0:
            names = "、".join(self.passive_skills_applied) or "被动"
            sign = "+" if self.passive_skill_bonus > 0 else ""
            skill_part += f"{sign}{self.passive_skill_bonus}被动({names}) "
        elif self.skill_bonus and not self.active_skill_bonus:
            skill_part = f"+{self.skill_bonus}技能 "
        situational_part = (
            f"+{self.situational_bonus}环境 " if self.situational_bonus else ""
        )
        total = self.check_total if self.check_total else self.roll.total
        return (
            f"{ability_label} 检定 {self.roll.describe()} {prof_part}{skill_part}"
            f"{situational_part}= {total} vs DC {self.dc} → {outcome}"
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
    ally_defs: list["AllyDefPatch"] = Field(default_factory=list)


class EnemyDefPatch(BaseModel):
    name: str = ""
    hp: int = 0
    ac: int = 12
    attack_damage: str = "1d6"
    attack_bonus: int = 3
    sp: int = 0
    sp_max: int = 0
    start_distance_m: int = 10
    start_x_m: int = 0
    start_y_m: int = 0
    use_dex: bool = False
    attack_range_normal_m: int = 0
    attack_range_max_m: int = 0

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
            use_dex=self.use_dex,
            attack_range_normal_m=max(0, self.attack_range_normal_m),
            attack_range_max_m=max(0, self.attack_range_max_m),
        )


class AllyDefPatch(EnemyDefPatch):
    """友方战斗单位定义（字段与 enemy_defs 相同）。"""

    def to_combat_ally(self) -> "CombatAlly":
        from game.models import CombatAlly

        hp = max(1, self.hp)
        sp = max(0, self.sp)
        sp_max = max(sp, self.sp_max) if self.sp_max > 0 else sp
        attack = (self.attack_damage or "1d6").strip()
        return CombatAlly(
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
            use_dex=self.use_dex,
            attack_range_normal_m=max(0, self.attack_range_normal_m),
            attack_range_max_m=max(0, self.attack_range_max_m),
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

    @model_validator(mode="after")
    def _require_description_on_add(self) -> Self:
        if self.action == "add" and not self.description.strip():
            raise ValueError("inventory add 必须填写 description")
        return self


class SkillPatch(BaseModel):
    action: Literal["add", "remove"] = "add"
    skill: str = ""
    description: str = ""
    kind: Literal["active", "passive"] | None = None


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


class BackgroundProcessPatch(BaseModel):
    id: str = ""
    label: str = ""
    duration_minutes: int = 1
    result_fact: str = ""
    blocks_actions: str = ""


class TimePatch(BaseModel):
    time_label: str = ""
    advance_minutes: int = 0
    advance_reason: str = ""
    deadlines: list[DeadlinePatch] = Field(default_factory=list)
    cancel_deadline_ids: list[str] = Field(default_factory=list)
    enforce_deadline_ids: list[str] = Field(default_factory=list)


class RerollPatch(BaseModel):
    grant: bool = False
    overturn_failure: bool = False
    adjusted_dc: int = 0
    ability: str = ""
    action_hint: str = ""
    reason: str = ""


class MemoryFactPatch(BaseModel):
    text: str = ""
    topic: str = ""
    tags: list[str] = Field(default_factory=list)

    @field_validator("topic", mode="before")
    @classmethod
    def _normalize_topic(cls, value) -> str:
        return normalize_topic(str(value or ""))


MemoryFactInput = Union[str, MemoryFactPatch]


class StatePatch(BaseModel):
    scene: ScenePatch | None = None
    npcs: list[NpcPatch] = Field(default_factory=list)
    quests: list[QuestPatch] = Field(default_factory=list)
    inventory: list[InventoryPatch] = Field(default_factory=list)
    equipment: list[EquipmentPatch] = Field(default_factory=list)
    skills: list[SkillPatch] = Field(default_factory=list)
    memory_facts: list[MemoryFactInput] = Field(default_factory=list)
    background_processes: list[BackgroundProcessPatch] = Field(default_factory=list)
    time: TimePatch | None = None
    end_combat: bool = False
    reroll: RerollPatch | None = None
    map_discovery: bool = False


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

    @property
    def has_tool_events(self) -> bool:
        return bool(self.tool_events)
