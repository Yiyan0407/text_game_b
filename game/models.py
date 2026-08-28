from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from game.active_gear import ActiveGearEntry, normalize_active_gear
from game.equipment import (
    EquipmentEntry,
    EquipmentSlot,
    infer_equipment_slot,
    is_valid_equipment_slot,
    normalize_equipment,
)
from game.inventory import (
    InventoryItem,
    merge_item_stacks,
    normalize_inventory_list,
    normalize_item_quantity_unit,
    _merge_description,
)
from game.skills import Skill, normalize_skills_list, parse_skill_text, split_skill_description
from game.effects import EntityEffects
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
    equipment: list[EquipmentEntry] = Field(default_factory=list)

    @field_validator("inventory", mode="before")
    @classmethod
    def _coerce_inventory(cls, value):
        return normalize_inventory_list(value)

    @field_validator("active_gear", mode="before")
    @classmethod
    def _coerce_active_gear(cls, value):
        return normalize_active_gear(value)

    @field_validator("equipment", mode="before")
    @classmethod
    def _coerce_equipment(cls, value):
        return normalize_equipment(value)

    @field_validator("skills", mode="before")
    @classmethod
    def _coerce_skills(cls, value):
        return normalize_skills_list(value)

    @model_validator(mode="after")
    def _migrate_legacy_active_gear(self) -> Self:
        for entry in list(self.active_gear):
            if self.find_inventory_item(entry.item_name) and not self.is_item_equipped(
                entry.item_name
            ):
                self.equip_item(entry.item_name, slot="hand")
        self.active_gear = []
        return self

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
        items = self.unequipped_inventory()
        if not items:
            if self.equipment:
                return "（已装备物品见装备栏，背包无额外物品）"
            return "（空，尚未获得任何物品）"
        return "；".join(item.format_full_line() for item in items)

    def format_equipment(self) -> str:
        self.prune_equipment()
        if not self.equipment:
            return "（无）"
        from game.equipment import SLOT_LABELS

        grouped = self.equipment_by_slot()
        parts: list[str] = []
        for slot, label in SLOT_LABELS.items():
            items = grouped.get(slot, [])
            if items:
                parts.append(f"{label}：{'；'.join(items)}")
            else:
                parts.append(f"{label}：（空）")
        return " | ".join(parts)

    def is_item_in_hand(self, item_name: str) -> bool:
        self.prune_equipment()
        return self.find_equipment_entry(item_name=item_name, slot="hand") is not None

    def is_item_active(self, item_name: str) -> bool:
        """兼容旧名：等同于是否装备在手持槽。"""
        return self.is_item_in_hand(item_name)

    def equipment_by_slot(self) -> dict[str, list[str]]:
        """按槽位分组的装备展示行（含数量、效果、描述）。"""
        from game.equipment import SLOT_LABELS

        self.prune_equipment()
        grouped: dict[str, list[str]] = {slot: [] for slot in SLOT_LABELS}
        for entry in self.equipment:
            item = self.find_inventory_item(entry.item_name)
            line = item.format_full_line() if item is not None else entry.item_name
            grouped.setdefault(entry.slot, []).append(line)
        return grouped

    def unequipped_inventory(self) -> list[InventoryItem]:
        """背包中尚未装备的物品（已装备的不重复展示）。"""
        self.prune_equipment()
        return [
            item
            for item in self.inventory
            if not self.is_item_equipped(item.name)
        ]

    def inventory_displays(self) -> list[str]:
        return [item.format_full_line() for item in self.unequipped_inventory()]

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

    def prune_equipment(self) -> None:
        names = {item.name for item in self.inventory}
        self.equipment = [
            entry for entry in self.equipment if entry.item_name in names
        ]

    def find_equipment_entry(
        self,
        *,
        item_name: str = "",
        slot: str = "",
    ) -> EquipmentEntry | None:
        self.prune_equipment()
        for entry in self.equipment:
            if slot and entry.slot != slot:
                continue
            if item_name and entry.item_name != item_name:
                if not fuzzy_match_name(item_name, entry.item_name):
                    continue
            return entry
        return None

    def is_item_equipped(self, item_name: str) -> bool:
        self.prune_equipment()
        return any(
            fuzzy_match_name(item_name, entry.item_name) for entry in self.equipment
        )

    def equip_item(
        self,
        item_ref: str,
        *,
        slot: EquipmentSlot | None = None,
    ) -> tuple[bool, str]:
        target = self.find_inventory_item(item_ref)
        if target is None:
            return False, f"背包中没有：{item_ref}"

        resolved = slot or infer_equipment_slot(target.name, target.description)
        if resolved is None:
            return False, f"无法判断装备槽位：{target.name}"

        self.prune_equipment()
        if self.is_item_equipped(target.name):
            return False, f"已装备：{target.name}"

        self.equipment.append(
            EquipmentEntry(slot=resolved, item_name=target.name)
        )
        entry = self.find_equipment_entry(item_name=target.name, slot=resolved)
        label = entry.format_line() if entry else target.name
        return True, f"装备：{label}"

    def unequip_item(
        self,
        item_ref: str = "",
        *,
        slot: str = "",
    ) -> tuple[bool, str]:
        if slot and is_valid_equipment_slot(slot):
            from game.equipment import coerce_equipment_slot

            resolved = coerce_equipment_slot(slot)
            removed: list[str] = []
            kept: list[EquipmentEntry] = []
            for entry in self.equipment:
                if entry.slot == resolved:
                    removed.append(entry.item_name)
                else:
                    kept.append(entry)
            if not removed:
                return False, f"未装备槽位：{resolved}"
            self.equipment = kept
            for name in removed:
                self._ensure_inventory_on_unequip(name)
            if len(removed) == 1:
                return True, f"卸下：{removed[0]}（回背包）"
            joined = "、".join(removed)
            return True, f"卸下：{joined}（回背包）"

        if not item_ref.strip():
            return False, "未指定要卸下的物品。"

        target_name = ""
        for entry in list(self.equipment):
            if fuzzy_match_name(item_ref, entry.item_name):
                target_name = entry.item_name
                self.equipment.remove(entry)
                break
        if not target_name:
            return False, f"未装备：{item_ref}"
        self._ensure_inventory_on_unequip(target_name)
        return True, f"卸下：{target_name}（回背包）"

    def _ensure_inventory_on_unequip(self, item_name: str) -> None:
        """卸下后物品应仍在背包；若缺失则补回（防止误删）。"""
        if not self.has_inventory_item(item_name):
            self.add_inventory_item(item_name, quantity=1)

    def clear_equipment_item(self, item_name: str) -> None:
        cleaned = item_name.strip()
        if not cleaned:
            return
        self.equipment = [
            entry for entry in self.equipment if entry.item_name != cleaned
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
        kind: str | None = None,
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
                item_kwargs: dict = {
                    "name": text,
                    "quantity": qty,
                    "unit": normalized_unit,
                    "description": description.strip(),
                }
                if kind in ("consumable", "durable", "document"):
                    item_kwargs["kind"] = kind
                incoming = InventoryItem(**item_kwargs)

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
            self.clear_equipment_item(target.name)
            return True, f"背包移除：{before}"

        target.quantity -= quantity
        return True, f"背包更新：{target.display()}（原 {before}）"

    def add_inventory_stack(self, label: str, quantity: int, unit: str = "枚") -> bool:
        label = label.strip()
        if not label or quantity <= 0:
            return False
        return self.add_inventory_item(label, quantity=quantity, unit=unit)

    def armor_class(self, defending: bool = False) -> int:
        from game.effect_resolver import sum_equipped_ac_bonus

        ac = 10 + self.modifier("dex") + sum_equipped_ac_bonus(self)
        if defending:
            ac += 2
        return ac

    def effective_max_hp(self) -> int:
        from game.effect_resolver import sum_equipped_max_hp_bonus

        return self.max_hp + sum_equipped_max_hp_bonus(self)

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
    status: Literal["pending", "due", "triggered", "resolved", "cancelled"] = "pending"
    consequence: str = ""
    created_at_minutes: int = 0
    fail_quest_ids: list[str] = Field(default_factory=list)
    hp_loss: int = 0


class CombatEnemy(BaseModel):
    name: str
    hp: int
    max_hp: int
    ac: int = 12
    initiative: int = 0
    attack_bonus: int = 3
    damage_notation: str = "1d6"
    attack_damage: str = ""
    sp: int = Field(default=0, ge=0)
    sp_max: int = Field(default=0, ge=0)
    start_distance_m: int = 10

    @model_validator(mode="after")
    def _sync_attack_damage(self) -> Self:
        if not self.attack_damage.strip():
            object.__setattr__(self, "attack_damage", self.damage_notation)
        if self.sp_max <= 0 and self.sp > 0:
            object.__setattr__(self, "sp_max", self.sp)
        return self

    def effective_attack_damage(self) -> str:
        return (self.attack_damage or self.damage_notation or "1d6").strip()


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
    movement_speed_m: int = 9
    movement_remaining_m: int = 9
    enemy_distances: dict[str, int] = Field(default_factory=dict)
    free_interact_used: bool = False
    smoke_cover_rounds: int = 0
    flash_disorient_rounds: int = 0

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
            from game.combat_modifiers import tick_tactical_effects

            tick_tactical_effects(self)
        if self.is_player_turn():
            self.defending = False
            self.action_used = False
            self.bonus_action_used = False
            self.movement_remaining_m = self.movement_speed_m
            self.free_interact_used = False

    def distance_to(self, enemy_name: str) -> int | None:
        enemy = self.get_enemy(enemy_name)
        if enemy is None:
            return None
        if enemy.name in self.enemy_distances:
            return self.enemy_distances[enemy.name]
        return enemy.start_distance_m

    def set_distance_to(self, enemy_name: str, meters: int) -> None:
        enemy = self.get_enemy(enemy_name)
        if enemy is None:
            return
        self.enemy_distances[enemy.name] = max(0, int(meters))

    def has_movement(self) -> bool:
        return self.movement_remaining_m > 0

    def spend_movement(self, meters: int) -> int:
        """消耗移动力，返回实际移动米数。"""
        meters = max(0, int(meters))
        if meters <= 0:
            return 0
        actual = min(meters, self.movement_remaining_m)
        self.movement_remaining_m -= actual
        return actual

    def has_main_action(self) -> bool:
        return not self.action_used

    def has_bonus_action(self) -> bool:
        return not self.bonus_action_used

    def has_free_interact(self) -> bool:
        return not self.free_interact_used

    def spend_free_interact(self) -> bool:
        if self.free_interact_used:
            return False
        self.free_interact_used = True
        return True

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
        move = f"{self.movement_remaining_m}/{self.movement_speed_m}m"
        free = "可用" if self.has_free_interact() else "已用"
        return (
            f"移动力：{move} | 免费互动：{free} | 主要动作：{main} | 附加动作：{bonus}"
        )

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
            if enemy.hp <= 0:
                status = "已倒"
            else:
                dist = self.enemy_distances.get(enemy.name)
                dist_text = f" · {dist}m" if dist is not None else ""
                status = f"HP {enemy.hp}/{enemy.max_hp} AC {enemy.ac}{dist_text}"
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
    story_start_absolute_minutes: int = 8 * 60
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
