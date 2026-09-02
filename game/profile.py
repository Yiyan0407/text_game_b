import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from config.settings import PROFILES_DIR, SAVES_DIR
from game.appearance import CharacterAppearance, parse_appearance_dict
from game.equipment import EquipmentEntry, normalize_equipment
from game.inventory import InventoryItem, merge_inventory_items, normalize_inventory_list
from game.skills import Skill, normalize_skills_list
from game.models import Character, GameState, compute_max_hp
from game.save import SaveGame, SaveManager, _normalize_save_payload
from game.scenario import Scenario

MAX_LOADOUT_ITEMS = 8
MAX_LOADOUT_SKILLS = 6


class CharacterLoadout(BaseModel):
    """开新战役时从角色库挑选携带的技能、物品与装备。"""

    skill_names: list[str] = Field(default_factory=list)
    item_names: list[str] = Field(default_factory=list)
    equipment: list[EquipmentEntry] = Field(default_factory=list)

    @field_validator("equipment", mode="before")
    @classmethod
    def _coerce_equipment(cls, value):
        return normalize_equipment(value)


def _merge_items_into_library(
    library: list[InventoryItem],
    incoming: list[InventoryItem],
) -> list[InventoryItem]:
    if not incoming:
        return library
    merged = [item.model_copy() for item in library]
    merged.extend(item.model_copy() for item in incoming)
    return merge_inventory_items(merged)


def _merge_equipment_into_library(
    library: list[EquipmentEntry],
    incoming: list[EquipmentEntry],
) -> list[EquipmentEntry]:
    if not incoming:
        return library
    seen = {(entry.slot, entry.item_name) for entry in library}
    merged = [entry.model_copy() for entry in library]
    for entry in incoming:
        key = (entry.slot, entry.item_name)
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry.model_copy())
    return merged


def _pick_library_items(
    library: list[InventoryItem],
    item_names: list[str],
) -> list[InventoryItem]:
    picked: list[InventoryItem] = []
    for ref in item_names:
        name = InventoryItem.name_from_ref(ref)
        if not name:
            continue
        for item in library:
            if item.name == name or item.matches(ref):
                picked.append(item.model_copy())
                break
    return picked


def _pick_library_skills(
    library: list[Skill],
    skill_names: list[str],
) -> list[Skill]:
    names = {name.strip() for name in skill_names if name.strip()}
    return [skill.model_copy() for skill in library if skill.name in names]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlayerProfile(BaseModel):
    profile_id: str
    name: str
    created_at: str


class CampaignRecord(BaseModel):
    scenario_id: str
    scenario_title: str
    status: Literal["active", "paused", "completed", "failed"] = "paused"
    summary: str = ""
    turn_count: int = 0
    last_played_at: str = ""


class CharacterCard(BaseModel):
    card_id: str
    name: str
    background: str = "一位初到此地的冒险者。"
    strength: int = Field(default=12, ge=3, le=18)
    dex: int = Field(default=12, ge=3, le=18)
    constitution: int = Field(default=12, ge=3, le=18)
    intelligence: int = Field(default=12, ge=3, le=18)
    wisdom: int = Field(default=12, ge=3, le=18)
    charisma: int = Field(default=12, ge=3, le=18)
    preferred_world_id: str = ""
    appearance: CharacterAppearance = Field(default_factory=CharacterAppearance)
    inventory: list[InventoryItem] = Field(default_factory=list)
    equipment: list[EquipmentEntry] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    notable_facts: list[str] = Field(default_factory=list)
    career_summary: str = ""
    campaign_history: list[CampaignRecord] = Field(default_factory=list)
    deceased: bool = False
    death_note: str = ""
    portrait_file: str = ""
    portrait_updated_at: str = ""
    created_at: str = ""
    updated_at: str = ""

    @field_validator("appearance", mode="before")
    @classmethod
    def _coerce_appearance(cls, value):
        if isinstance(value, CharacterAppearance):
            return value
        return parse_appearance_dict(value if isinstance(value, dict) else None)

    @field_validator("inventory", mode="before")
    @classmethod
    def _coerce_inventory(cls, value):
        return normalize_inventory_list(value)

    @field_validator("equipment", mode="before")
    @classmethod
    def _coerce_equipment(cls, value):
        return normalize_equipment(value)

    @field_validator("skills", mode="before")
    @classmethod
    def _coerce_skills(cls, value):
        return normalize_skills_list(value)

    @classmethod
    def from_character(
        cls,
        character: Character,
        *,
        card_id: str | None = None,
        preferred_world_id: str = "",
    ) -> "CharacterCard":
        now = _utc_now()
        return cls(
            card_id=card_id or str(uuid.uuid4()),
            name=character.name,
            background=character.background,
            strength=character.strength,
            dex=character.dex,
            constitution=character.constitution,
            intelligence=character.intelligence,
            wisdom=character.wisdom,
            charisma=character.charisma,
            preferred_world_id=preferred_world_id,
            inventory=[item.model_copy() for item in character.inventory],
            equipment=[entry.model_copy() for entry in character.equipment],
            skills=[skill.model_copy() for skill in character.skills],
            created_at=now,
            updated_at=now,
        )

    def has_career(self) -> bool:
        if self.deceased:
            return True
        if self.skills or self.inventory or self.notable_facts or self.career_summary.strip():
            return True
        return any(
            record.summary.strip() or record.status != "active"
            for record in self.campaign_history
        )

    def is_playable(self) -> bool:
        return not self.deceased

    def library_loadout(self) -> CharacterLoadout:
        """测试/工具：携带库中全部技能与物品。"""
        return CharacterLoadout(
            skill_names=[skill.name for skill in self.skills],
            item_names=[item.name for item in self.inventory],
            equipment=[entry.model_copy() for entry in self.equipment],
        )

    def to_runtime_character(self, loadout: CharacterLoadout | None = None) -> Character:
        loadout = loadout or CharacterLoadout()
        max_hp = compute_max_hp(self.constitution)
        inventory = _pick_library_items(self.inventory, loadout.item_names)
        skills = _pick_library_skills(self.skills, loadout.skill_names)
        picked_item_names = {item.name for item in inventory}
        equipment = [
            entry.model_copy()
            for entry in loadout.equipment
            if entry.item_name in picked_item_names
        ]
        return Character(
            name=self.name,
            background=self.background,
            strength=self.strength,
            dex=self.dex,
            constitution=self.constitution,
            intelligence=self.intelligence,
            wisdom=self.wisdom,
            charisma=self.charisma,
            hp=max_hp,
            max_hp=max_hp,
            inventory=inventory,
            skills=skills,
            equipment=equipment,
        )

    def format_career_context(self, loadout: CharacterLoadout | None = None) -> str:
        if not self.has_career():
            return ""
        lines = ["【长期角色履历】", f"姓名：{self.name}", f"背景：{self.background}"]
        if self.campaign_history:
            lines.append("过往战役：")
            for record in self.campaign_history[-5:]:
                if not record.summary.strip() and record.status == "active" and record.turn_count == 0:
                    continue
                status_label = {
                    "active": "进行中",
                    "paused": "暂停",
                    "completed": "已完成",
                    "failed": "阵亡",
                }.get(record.status, record.status)
                summary = record.summary.strip() or "（尚无摘要）"
                lines.append(
                    f"- 《{record.scenario_title}》[{status_label}·{record.turn_count}回合] {summary}"
                )
        elif self.career_summary.strip():
            lines.append(f"生涯摘要：{self.career_summary.strip()}")
        skills_to_show = (
            _pick_library_skills(self.skills, loadout.skill_names)
            if loadout is not None
            else list(self.skills)
        )
        items_to_show = (
            _pick_library_items(self.inventory, loadout.item_names)
            if loadout is not None
            else list(self.inventory)
        )
        if skills_to_show:
            lines.append(
                f"本场携带技能：{'；'.join(skill.format_detail() for skill in skills_to_show)}"
            )
        if loadout is not None and len(self.skills) > len(skills_to_show):
            lines.append(
                f"（库中另有 {len(self.skills) - len(skills_to_show)} 项技能未携带）"
            )
        if items_to_show:
            lines.append(
                f"本场携带物品：{'；'.join(item.format_detail() for item in items_to_show)}"
            )
        if loadout is not None and len(self.inventory) > len(items_to_show):
            lines.append(
                f"（库中另有 {len(self.inventory) - len(items_to_show)} 件物品未携带）"
            )
        if self.notable_facts:
            lines.append("关键记忆：")
            for fact in self.notable_facts[-8:]:
                lines.append(f"- {fact}")
        return "\n".join(lines)


def _find_active_campaign(card: CharacterCard, scenario_id: str) -> CampaignRecord | None:
    for record in reversed(card.campaign_history):
        if record.scenario_id == scenario_id and record.status == "active":
            return record
    return None


def _find_campaign_for_sync(card: CharacterCard, scenario_id: str) -> CampaignRecord | None:
    """同步时更新当前战役记录；阵亡后 status=failed 仍须命中同一条，避免重复追加。"""
    active = _find_active_campaign(card, scenario_id)
    if active is not None:
        return active
    for record in reversed(card.campaign_history):
        if record.scenario_id == scenario_id:
            return record
    return None


def _consolidate_campaign_history(card: CharacterCard) -> None:
    """合并同一模组+同一状态的重复履历（历史 bug 或多次存档遗留）。"""
    merged: list[CampaignRecord] = []
    index_by_key: dict[tuple[str, str], int] = {}

    for record in card.campaign_history:
        key = (record.scenario_id, record.status)
        if key not in index_by_key:
            index_by_key[key] = len(merged)
            merged.append(record.model_copy())
            continue
        existing = merged[index_by_key[key]]
        existing.turn_count = max(existing.turn_count, record.turn_count)
        if record.summary.strip():
            existing.summary = record.summary
        if record.scenario_title.strip():
            existing.scenario_title = record.scenario_title
        if record.last_played_at > existing.last_played_at:
            existing.last_played_at = record.last_played_at

    card.campaign_history = merged


def _rebuild_career_summary(card: CharacterCard) -> str:
    parts: list[str] = []
    for record in card.campaign_history:
        if not record.summary.strip():
            continue
        parts.append(f"《{record.scenario_title}》：{record.summary.strip()}")
    return " ".join(parts[-5:])


def prepare_card_for_new_campaign(card: CharacterCard, scenario: Scenario) -> None:
    if card.deceased:
        raise ValueError(f"角色「{card.name}」已死亡，无法开始新冒险。")
    for record in card.campaign_history:
        if record.status == "active":
            record.status = "paused"
    card.campaign_history.append(
        CampaignRecord(
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            status="active",
            last_played_at=_utc_now(),
        )
    )


def sync_card_from_adventure(
    card: CharacterCard,
    character: Character,
    game_state: GameState,
    scenario: Scenario,
    *,
    finalize: bool = False,
) -> CharacterCard:
    card.name = character.name
    card.background = character.background

    merged_skills = [skill.model_copy() for skill in card.skills]
    for skill in character.skills:
        existing = next(
            (entry for entry in merged_skills if entry.name == skill.name),
            None,
        )
        if existing is None:
            merged_skills.append(skill.model_copy())
        elif skill.description and not existing.description:
            existing.description = skill.description
    card.skills = merged_skills
    card.inventory = _merge_items_into_library(card.inventory, list(character.inventory))
    card.equipment = _merge_equipment_into_library(
        card.equipment, list(character.equipment)
    )

    for fact in game_state.player_memory_entries():
        if fact.text not in card.notable_facts:
            card.notable_facts.append(fact.text)
    if len(card.notable_facts) > 30:
        card.notable_facts = card.notable_facts[-30:]

    record = _find_campaign_for_sync(card, scenario.id)
    if record is None:
        if not character.is_alive():
            initial_status = "failed"
        elif finalize:
            initial_status = "paused"
        else:
            initial_status = "active"
        record = CampaignRecord(
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            status=initial_status,
            last_played_at=_utc_now(),
        )
        card.campaign_history.append(record)
    record.scenario_title = scenario.title
    record.turn_count = game_state.turn_count
    record.last_played_at = _utc_now()
    if game_state.story_summary.strip():
        record.summary = game_state.story_summary.strip()

    if not character.is_alive():
        card.deceased = True
        finalize = True
        if game_state.story_summary.strip():
            card.death_note = game_state.story_summary.strip()[:500]
        elif not card.death_note.strip():
            card.death_note = (
                f"在《{scenario.title}》中阵亡（第 {game_state.turn_count} 回合）。"
            )
        record.status = "failed"
    elif finalize:
        record.status = "paused"

    _consolidate_campaign_history(card)
    card.career_summary = _rebuild_career_summary(card)
    return card


def card_to_character(card: CharacterCard) -> Character:
    return card.to_runtime_character()


class ProfileManager:
    def __init__(self, profiles_dir: Path | None = None):
        self.profiles_dir = profiles_dir or PROFILES_DIR
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def _profile_path(self, profile_id: str) -> Path:
        return self.profiles_dir / profile_id / "profile.json"

    def _characters_dir(self, profile_id: str) -> Path:
        return self.profiles_dir / profile_id / "characters"

    def _saves_dir(self, profile_id: str) -> Path:
        return self.profiles_dir / profile_id / "saves"

    def _character_assets_dir(self, profile_id: str, card_id: str) -> Path:
        return self._characters_dir(profile_id) / card_id

    def portrait_file_path(self, profile_id: str, card: CharacterCard) -> Path | None:
        if not card.portrait_file.strip():
            return None
        return self._character_assets_dir(profile_id, card.card_id) / card.portrait_file

    def save_portrait(
        self,
        profile_id: str,
        card: CharacterCard,
        image_bytes: bytes,
        *,
        filename: str = "portrait.png",
    ) -> CharacterCard:
        assets_dir = self._character_assets_dir(profile_id, card.card_id)
        assets_dir.mkdir(parents=True, exist_ok=True)
        path = assets_dir / filename
        path.write_bytes(image_bytes)
        card.portrait_file = filename
        card.portrait_updated_at = _utc_now()
        self.save_character_card(profile_id, card)
        return card

    def list_profiles(self) -> list[PlayerProfile]:
        profiles: list[PlayerProfile] = []
        for path in self.profiles_dir.iterdir():
            if not path.is_dir():
                continue
            profile_file = path / "profile.json"
            if not profile_file.exists():
                continue
            try:
                profiles.append(
                    PlayerProfile.model_validate(
                        json.loads(profile_file.read_text(encoding="utf-8"))
                    )
                )
            except Exception:
                continue
        profiles.sort(key=lambda p: p.created_at)
        return profiles

    def create_profile(self, name: str) -> PlayerProfile:
        profile = PlayerProfile(
            profile_id=str(uuid.uuid4()),
            name=name.strip() or "未命名档案",
            created_at=_utc_now(),
        )
        profile_dir = self.profiles_dir / profile.profile_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._characters_dir(profile.profile_id).mkdir(parents=True, exist_ok=True)
        self._saves_dir(profile.profile_id).mkdir(parents=True, exist_ok=True)
        self._profile_path(profile.profile_id).write_text(
            profile.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return profile

    def load_profile(self, profile_id: str) -> PlayerProfile:
        path = self._profile_path(profile_id)
        if not path.exists():
            raise FileNotFoundError(f"档案不存在: {profile_id}")
        return PlayerProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def delete_profile(self, profile_id: str) -> None:
        profile_dir = self.profiles_dir / profile_id
        if profile_dir.exists():
            shutil.rmtree(profile_dir)

    def get_save_manager(self, profile_id: str) -> SaveManager:
        saves_dir = self._saves_dir(profile_id)
        saves_dir.mkdir(parents=True, exist_ok=True)
        return SaveManager(saves_dir=saves_dir, profile_id=profile_id)

    def _repair_card_if_needed(self, profile_id: str, card: CharacterCard) -> CharacterCard:
        before = len(card.campaign_history)
        _consolidate_campaign_history(card)
        if len(card.campaign_history) < before:
            self.save_character_card(profile_id, card)
        return card

    def list_character_cards(self, profile_id: str) -> list[CharacterCard]:
        cards_dir = self._characters_dir(profile_id)
        cards_dir.mkdir(parents=True, exist_ok=True)
        cards: list[CharacterCard] = []
        for path in cards_dir.glob("*.json"):
            try:
                card = CharacterCard.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
                cards.append(self._repair_card_if_needed(profile_id, card))
            except Exception:
                continue
        cards.sort(key=lambda c: c.updated_at or c.created_at, reverse=True)
        return cards

    def save_character_card(self, profile_id: str, card: CharacterCard) -> Path:
        cards_dir = self._characters_dir(profile_id)
        cards_dir.mkdir(parents=True, exist_ok=True)
        card.updated_at = _utc_now()
        if not card.created_at:
            card.created_at = card.updated_at
        path = cards_dir / f"{card.card_id}.json"
        path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_character_card(self, profile_id: str, card_id: str) -> CharacterCard:
        path = self._characters_dir(profile_id) / f"{card_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"角色卡不存在: {card_id}")
        card = CharacterCard.model_validate(json.loads(path.read_text(encoding="utf-8")))
        return self._repair_card_if_needed(profile_id, card)

    def delete_character_card(self, profile_id: str, card_id: str) -> int:
        """删除角色卡及其关联存档（按 character_id）。返回删除的存档数量。"""
        save_manager = self.get_save_manager(profile_id)
        deleted_saves = save_manager.delete_by_character_id(card_id)
        assets_dir = self._character_assets_dir(profile_id, card_id)
        if assets_dir.exists():
            shutil.rmtree(assets_dir)
        path = self._characters_dir(profile_id) / f"{card_id}.json"
        if path.exists():
            path.unlink()
        return deleted_saves

    def count_saves_for_character(self, profile_id: str, card_id: str) -> int:
        return len(self.get_save_manager(profile_id).list_save_ids_for_character(card_id))

    def migrate_legacy_saves(self) -> PlayerProfile | None:
        """将旧版 data/saves/ 下的存档迁入默认档案（仅执行一次）。"""
        if not SAVES_DIR.exists():
            return None
        legacy_files = list(SAVES_DIR.glob("*.json"))
        if not legacy_files:
            return None

        profile = self.create_profile("默认档案")
        save_manager = self.get_save_manager(profile.profile_id)
        migrated_paths: list = []

        for legacy_path in legacy_files:
            try:
                raw = json.loads(legacy_path.read_text(encoding="utf-8"))
                payload = _normalize_save_payload(raw)
                payload["profile_id"] = profile.profile_id
                if not payload.get("character_id") and payload.get("character"):
                    card = CharacterCard.from_character(
                        Character.model_validate(payload["character"])
                    )
                    self.save_character_card(profile.profile_id, card)
                    payload["character_id"] = card.card_id
                save_game = SaveGame.model_validate(payload)
                save_manager.save(save_game)
                migrated_paths.append(legacy_path)
            except Exception:
                continue

        for legacy_path in migrated_paths:
            try:
                legacy_path.unlink()
            except OSError:
                pass

        return profile

    def ensure_default_profile(self) -> PlayerProfile:
        profiles = self.list_profiles()
        if profiles:
            return profiles[0]
        migrated = self.migrate_legacy_saves()
        if migrated:
            return migrated
        return self.create_profile("默认档案")
