from pydantic import BaseModel, Field

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
    inventory: list[str] = Field(default_factory=list)

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
        return "、".join(self.inventory)

    def add_inventory_item(self, item: str) -> bool:
        item = item.strip()
        if not item or item in self.inventory:
            return False
        self.inventory.append(item)
        return True

    def remove_inventory_item(self, item: str) -> bool:
        item = item.strip()
        if item not in self.inventory:
            return False
        self.inventory.remove(item)
        return True

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


class CombatEnemy(BaseModel):
    name: str
    hp: int
    max_hp: int
    ac: int = 12
    initiative: int = 0


class CombatState(BaseModel):
    active: bool = False
    round: int = 1
    enemies: list[CombatEnemy] = Field(default_factory=list)
    player_initiative: int = 0
    turn_order: list[str] = Field(default_factory=list)

    def format_for_prompt(self) -> str:
        if not self.active:
            return "战斗：未进行"
        lines = [f"战斗进行中 — 第 {self.round} 回合"]
        lines.append(f"先攻顺序：{' → '.join(self.turn_order)}")
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
        return None


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
        lines = [f"当前场景：{self.current_scene}（ID: {self.scene_id}）"]
        lines.append(f"已进行回合：{self.turn_count}")

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

    def upsert_npc(self, name: str, attitude: str, notes: str = "") -> None:
        for npc in self.npcs:
            if npc.name == name:
                npc.attitude = attitude
                if notes:
                    npc.notes = notes
                return
        self.npcs.append(NPCRelation(name=name, attitude=attitude, notes=notes))

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
