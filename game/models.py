from typing import Literal

from pydantic import BaseModel, Field, field_validator

from game.active_gear import ActiveGearEntry, normalize_active_gear
from game.inventory import (
    InventoryItem,
    merge_item_stacks,
    normalize_inventory_list,
    normalize_item_quantity_unit,
    _merge_description,
)
from game.skills import Skill, normalize_skills_list, parse_skill_text, split_skill_description
from game.item_kinds import infer_gear_slot
from game.text_match import fuzzy_match_name

ABILITY_ORDER: tuple[tuple[str, str, str], ...] = (
    ("str", "strength", "力量"),
    ("dex", "dex", "敏捷"),
    ("con", "constitution", "体质"),
    ("int", "intelligence", "智力"),
    ("wis", "wisdom", "感知"),
    ("cha", "charisma", "魅力"),
)

ABILITY_FIELDS = {key: field for key, field, _ in ABILITY_ORDER}
ABILITY_LABELS = {key: label for key, _, label in ABILITY_ORDER}


def compute_max_hp(constitution: int) -> int:
    con_mod = (constitution - 10) // 2
    return max(8, 10 + con_mod)


class Character(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    background: str = Field(default="一位初到灰港的冒险者。", max_length=500)
    strength: int = Field(default=12, ge=3, le=18)
    dex: int = Field(default=12, ge=3, le=18)
    constitution: int = Field(default=12, ge=3, le=18)
    intelligence: int = Field(default=12, ge=3, le=18)
    wisdom: int = Field(default=12, ge=3, le=18)
    charisma: int = Field(default=12, ge=3, le=18)
    hp: int = Field(default=20, ge=1)
    max_hp: int = Field(default=20, ge=1)
    inventory: list[InventoryItem] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    active_gear: list[ActiveGearEntry] = Field(default_factory=list)

    @field_validator("inventory", mode="before")
    @classmethod
    def _coerce_inventory(cls, value):
        return normalize_inventory_list(value)

    @field_validator("active_gear", mode="before")
    @classmethod
    def _coerce_active_gear(cls, value):
        return normalize_active_gear(value)

    @field_validator("skills", mode="before")
    @classmethod
    def _coerce_skills(cls, value):
        return normalize_skills_list(value)

    def modifier(self, attr: str) -> int:
        field = ABILITY_FIELDS.get(attr.lower(), attr.lower())
        value = getattr(self, field)
        return (value - 10) // 2

    def format_abilities(self) -> str:
        parts = []
        for key, field, label in ABILITY_ORDER:
            value = getattr(self, field)
            mod = self.modifier(key)
            parts.append(f"{label}({key.upper()}) {value}（{mod:+d}）")
        return " | ".join(parts)

    def format_inventory(self) -> str:
        if not self.inventory:
            return "（空，尚未获得任何物品）"
        return "；".join(item.format_detail() for item in self.inventory)

    def format_active_gear(self) -> str:
        self.prune_active_gear()
        if not self.active_gear:
            return "（无）"
        return "；".join(entry.format_line() for entry in self.active_gear)

    def inventory_displays(self) -> list[str]:
        return [item.format_detail() for item in self.inventory]

    def find_inventory_item(self, item_ref: str) -> InventoryItem | None:
        for item in self.inventory:
            if item.matches(item_ref):
                return item
        return None

    def has_inventory_item(self, item_ref: str) -> bool:
        return self.find_inventory_item(item_ref) is not None

    def has_sufficient_inventory(self, item_ref: str, quantity: int = 1) -> bool:
        target = self.find_inventory_item(item_ref)
        return target is not None and target.quantity >= quantity

    def prune_active_gear(self) -> None:
        names = {item.name for item in self.inventory}
        self.active_gear = [
            entry for entry in self.active_gear if entry.item_name in names
        ]

    def find_active_gear_slot(self, slot: str) -> ActiveGearEntry | None:
        for entry in self.active_gear:
            if entry.slot == slot:
                return entry
        return None

    def is_item_active(self, item_name: str) -> bool:
        self.prune_active_gear()
        return any(entry.item_name == item_name for entry in self.active_gear)

    def set_active_gear(self, item: InventoryItem) -> str:
        slot = infer_gear_slot(item.name, item.kind)
        if slot is None:
            return f"使用：{item.name}"
        self.prune_active_gear()
        self.active_gear = [entry for entry in self.active_gear if entry.slot != slot]
        self.active_gear.append(ActiveGearEntry(slot=slot, item_name=item.name))
        status = next(
            entry.format_line() for entry in self.active_gear if entry.item_name == item.name
        )
        return f"持用：{status}"

    def clear_active_gear_item(self, item_name: str) -> None:
        self.active_gear = [
            entry for entry in self.active_gear if entry.item_name != item_name.strip()
        ]

    def format_skills(self) -> str:
        if not self.skills:
            return "（无）"
        return "；".join(skill.format_detail() for skill in self.skills)

    def skill_names(self) -> list[str]:
        return [skill.name for skill in self.skills]

    def find_skill(self, skill_ref: str) -> Skill | None:
        for skill in self.skills:
            if fuzzy_match_name(skill_ref, skill.name):
                return skill
        return None

    def has_skill(self, skill_ref: str) -> bool:
        return self.find_skill(skill_ref) is not None

    def add_skill(self, skill: str | Skill, description: str = "") -> bool:
        if isinstance(skill, Skill):
            incoming = split_skill_description(skill.model_copy())
        else:
            text = skill.strip()
            if not text:
                return False
            incoming = parse_skill_text(text, description=description)

        existing = self.find_skill(incoming.name)
        if existing:
            if incoming.description and not existing.description:
                existing.description = incoming.description
                return True
            return False

        self.skills.append(incoming)
        return True

    def remove_skill(self, skill_ref: str) -> bool:
        target = self.find_skill(skill_ref)
        if target is None:
            return False
        self.skills.remove(target)
        return True

    def add_inventory_item(
        self,
        item: str | InventoryItem,
        quantity: int = 1,
        unit: str = "个",
        description: str = "",
    ) -> bool:
        if isinstance(item, InventoryItem):
            incoming = item.model_copy()
        else:
            text = item.strip()
            if not text:
                return False
            if "（" in text and text.endswith("）"):
                incoming = InventoryItem.parse(text)
                if description.strip():
                    incoming.description = description.strip()
            else:
                qty, normalized_unit = normalize_item_quantity_unit(quantity, unit)
                incoming = InventoryItem(
                    name=text,
                    quantity=qty,
                    unit=normalized_unit,
                    description=description.strip(),
                )

        qty, normalized_unit = normalize_item_quantity_unit(
            incoming.quantity, incoming.unit
        )
        incoming.quantity = qty
        incoming.unit = normalized_unit

        for existing in self.inventory:
            if existing.name == incoming.name and existing.unit == incoming.unit:
                existing.quantity += incoming.quantity
                _merge_description(existing, incoming)
                return True

        for existing in self.inventory:
            if existing.name == incoming.name:
                merge_item_stacks(existing, incoming)
                return True

        self.inventory.append(incoming)
        return True

    def remove_inventory_item(
        self,
        item_ref: str,
        quantity: int = 1,
        unit: str | None = None,
    ) -> bool:
        ok, _ = self.consume_inventory_quantity(item_ref, quantity, unit=unit)
        return ok

    def consume_inventory_quantity(
        self,
        item_ref: str,
        quantity: int = 1,
        unit: str | None = None,
    ) -> tuple[bool, str]:
        item_ref = item_ref.strip()
        if not item_ref or quantity <= 0:
            return False, "物品或数量无效。"

        target = self.find_inventory_item(item_ref)
        if target is None:
            return False, f"背包中没有：{item_ref}"
        if unit is not None and target.unit != unit:
            return False, f"背包中没有：{item_ref}"

        before = target.display()
        if quantity > target.quantity:
            return False, f"背包中 {before} 数量不足。"

        if quantity == target.quantity:
            self.inventory.remove(target)
            self.clear_active_gear_item(target.name)
            return True, f"背包移除：{before}"

        target.quantity -= quantity
        return True, f"背包更新：{target.display()}（原 {before}）"

    def add_inventory_stack(self, label: str, quantity: int, unit: str = "枚") -> bool:
        label = label.strip()
        if not label or quantity <= 0:
            return False
        return self.add_inventory_item(label, quantity=quantity, unit=unit)

    def armor_class(self, defending: bool = False) -> int:
        ac = 10 + self.modifier("dex")
        if defending:
            ac += 2
        return ac

    def summary(self) -> str:
        attrs = " ".join(
            f"{key.upper()} {getattr(self, field)}"
            for key, field, _ in ABILITY_ORDER
        )
        return f"{self.name} | HP {self.hp}/{self.max_hp} | {attrs}"


class NPCRelation(BaseModel):
    name: str
    attitude: str = "unknown"  # friendly | neutral | hostile | unknown
    notes: str = ""


class Quest(BaseModel):
    id: str
    title: str
    status: str = "active"  # active | completed | failed
    description: str = ""


class NarrativeDeadline(BaseModel):
    id: str
    label: str
    due_at_minutes: int = 0
    status: Literal["pending", "triggered", "cancelled"] = "pending"
    consequence: str = ""
    created_at_minutes: int = 0


class CombatEnemy(BaseModel):
    name: str
    hp: int
    max_hp: int
    ac: int = 12
    initiative: int = 0
    attack_bonus: int = 3
    damage_notation: str = "1d6"


class CombatState(BaseModel):
    active: bool = False
    round: int = 1
    enemies: list[CombatEnemy] = Field(default_factory=list)
    player_initiative: int = 0
    turn_order: list[str] = Field(default_factory=list)
    turn_index: int = 0
    defending: bool = False
    action_used: bool = False
    bonus_action_used: bool = False

    def current_actor(self) -> str:
        if not self.turn_order:
            return "player"
        return self.turn_order[self.turn_index % len(self.turn_order)]

    def is_player_turn(self) -> bool:
        return self.current_actor() == "player"

    def advance_turn(self) -> None:
        if not self.turn_order:
            return
        self.turn_index = (self.turn_index + 1) % len(self.turn_order)
        if self.turn_index == 0:
            self.round += 1
        self.defending = False
        if self.is_player_turn():
            self.action_used = False
            self.bonus_action_used = False

    def has_main_action(self) -> bool:
        return not self.action_used

    def has_bonus_action(self) -> bool:
        return not self.bonus_action_used

    def spend_action(self, cost: str) -> bool:
        if cost == "free":
            return True
        if cost == "main":
            if self.action_used:
                return False
            self.action_used = True
            return True
        if cost == "bonus":
            if self.bonus_action_used:
                return False
            self.bonus_action_used = True
            return True
        return False

    def format_action_economy(self) -> str:
        main = "可用" if self.has_main_action() else "已用"
        bonus = "可用" if self.has_bonus_action() else "已用"
        return f"主要动作：{main} | 附加动作：{bonus}"

    def format_for_prompt(self) -> str:
        if not self.active:
            return "战斗：未进行"
        actor = self.current_actor()
        actor_label = "玩家" if actor == "player" else actor
        lines = [
            f"战斗进行中 — 第 {self.round} 回合",
            f"当前行动者：{actor_label}",
            f"先攻顺序：{' → '.join(self.turn_order)}",
        ]
        if self.is_player_turn():
            lines.append(self.format_action_economy())
        if self.defending:
            lines.append("玩家处于防御姿态（AC+2）")
        for enemy in self.enemies:
            status = "已倒" if enemy.hp <= 0 else f"HP {enemy.hp}/{enemy.max_hp} AC {enemy.ac}"
            lines.append(f"- {enemy.name}：{status}")
        return "\n".join(lines)

    def living_enemies(self) -> list[CombatEnemy]:
        return [e for e in self.enemies if e.hp > 0]

    def get_enemy(self, name: str) -> CombatEnemy | None:
        for enemy in self.enemies:
            if enemy.name == name:
                return enemy
        for enemy in self.enemies:
            if fuzzy_match_name(name, enemy.name):
                return enemy
        return None

    def living_enemy_names(self) -> list[str]:
        return [e.name for e in self.living_enemies()]


def _default_quests() -> list[Quest]:
    return []


class GameState(BaseModel):
    started: bool = False
    scenario_id: str = ""
    scene_id: str = "tavern_seagull"
    current_scene: str = "灰港·海鸥尾酒馆"
    active_quests: list[Quest] = Field(default_factory=_default_quests)
    npcs: list[NPCRelation] = Field(default_factory=list)
    story_summary: str = ""
    chapter_summaries: list[str] = Field(default_factory=list)
    memory_facts: list[str] = Field(default_factory=list)
    turn_count: int = 0
    last_summarized_turn: int = 0
    last_chapter_turn: int = 0
    combat: CombatState | None = None
    scene_image_url: str = ""
    elapsed_minutes: int = 0
    narrative_time_label: str = ""
    deadlines: list[NarrativeDeadline] = Field(default_factory=list)

    def add_memory_facts(self, new_facts: list[str], max_facts: int) -> None:
        for fact in new_facts:
            fact = fact.strip()
            if not fact:
                continue
            if any(fact in existing or existing in fact for existing in self.memory_facts):
                continue
            self.memory_facts.append(fact)
        if len(self.memory_facts) > max_facts:
            self.memory_facts = self.memory_facts[-max_facts:]

    def format_for_prompt(self) -> str:
        from game.narrative_time import format_narrative_time_context

        lines = [f"当前场景：{self.current_scene}（ID: {self.scene_id}）"]
        lines.append(f"已进行回合：{self.turn_count}")
        lines.append("【叙事时间】")
        lines.append(format_narrative_time_context(self))

        if self.combat and self.combat.active:
            lines.append(self.combat.format_for_prompt())

        if self.memory_facts:
            lines.append("【关键事实 — 不可矛盾】")
            for fact in self.memory_facts[-20:]:
                lines.append(f"- {fact}")

        if self.chapter_summaries:
            lines.append("【章节回顾 — 较早剧情】")
            for chapter in self.chapter_summaries[-3:]:
                lines.append(chapter)

        if self.story_summary:
            lines.append(f"【剧情总摘要 — 长期记忆】\n{self.story_summary}")

        active = [q for q in self.active_quests if q.status == "active"]
        if active:
            lines.append("进行中的任务：")
            for quest in active:
                lines.append(f"- [{quest.id}] {quest.title}：{quest.description}")

        completed = [q for q in self.active_quests if q.status != "active"]
        if completed:
            lines.append("已结束任务：")
            for quest in completed:
                lines.append(f"- [{quest.id}] {quest.title}（{quest.status}）")

        if self.npcs:
            lines.append("已知 NPC：")
            for npc in self.npcs:
                note = f" — {npc.notes}" if npc.notes else ""
                lines.append(f"- {npc.name}（{npc.attitude}）{note}")

        return "\n".join(lines)

    def get_quest(self, quest_id: str) -> Quest | None:
        for quest in self.active_quests:
            if quest.id == quest_id:
                return quest
        return None

    def find_npc(self, name_ref: str) -> NPCRelation | None:
        from game.npc_merge import find_npc_by_name

        return find_npc_by_name(self.npcs, name_ref)

    def dedupe_npcs(self) -> None:
        from game.npc_merge import dedupe_npc_list

        self.npcs = dedupe_npc_list(self.npcs)

    def upsert_npc(self, name: str, attitude: str, notes: str = "") -> None:
        from game.npc_merge import find_npc_by_name, merge_npc_notes, preferred_npc_name

        cleaned = name.strip()
        if not cleaned:
            return
        existing = find_npc_by_name(self.npcs, cleaned)
        if existing is not None:
            existing.name = preferred_npc_name(existing.name, cleaned)
            existing.attitude = attitude
            if notes.strip():
                existing.notes = merge_npc_notes(existing.notes, notes)
            return
        self.npcs.append(NPCRelation(name=cleaned, attitude=attitude, notes=notes.strip()))

    def upsert_quest(
        self,
        quest_id: str,
        title: str,
        status: str,
        description: str = "",
    ) -> None:
        quest = self.get_quest(quest_id)
        if quest:
            quest.title = title
            quest.status = status
            if description:
                quest.description = description
            return
        self.active_quests.append(
            Quest(id=quest_id, title=title, status=status, description=description)
        )

    def is_in_combat(self) -> bool:
        return bool(self.combat and self.combat.active)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class DiceRoll(BaseModel):
    notation: str
    rolls: list[int]
    modifier: int = 0
    total: int

    def describe(self) -> str:
        rolls_text = "+".join(str(r) for r in self.rolls)
        if self.modifier:
            sign = "+" if self.modifier >= 0 else ""
            return f"{self.notation} → [{rolls_text}]{sign}{self.modifier} = {self.total}"
        return f"{self.notation} → [{rolls_text}] = {self.total}"
