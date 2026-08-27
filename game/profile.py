import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from config.settings import PROFILES_DIR, SAVES_DIR
from game.inventory import InventoryItem, normalize_inventory_list
from game.models import Character, GameState, compute_max_hp
from game.save import SaveGame, SaveManager, _normalize_save_payload
from game.scenario import Scenario


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlayerProfile(BaseModel):
    profile_id: str
    name: str
    created_at: str


class CampaignRecord(BaseModel):
    scenario_id: str
    scenario_title: str
    status: Literal["active", "paused", "completed"] = "paused"
    summary: str = ""
    turn_count: int = 0
    last_played_at: str = ""


class CharacterCard(BaseModel):
    card_id: str
    name: str
    background: str = "一位初到灰港的冒险者。"
    strength: int = Field(default=12, ge=3, le=18)
    dex: int = Field(default=12, ge=3, le=18)
    constitution: int = Field(default=12, ge=3, le=18)
    intelligence: int = Field(default=12, ge=3, le=18)
    wisdom: int = Field(default=12, ge=3, le=18)
    charisma: int = Field(default=12, ge=3, le=18)
    preferred_world_id: str = ""
    inventory: list[InventoryItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    notable_facts: list[str] = Field(default_factory=list)
    career_summary: str = ""
    campaign_history: list[CampaignRecord] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @field_validator("inventory", mode="before")
    @classmethod
    def _coerce_inventory(cls, value):
        return normalize_inventory_list(value)

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
            skills=list(character.skills),
            created_at=now,
            updated_at=now,
        )

    def has_career(self) -> bool:
        if self.skills or self.inventory or self.notable_facts or self.career_summary.strip():
            return True
        return any(
            record.summary.strip() or record.status != "active"
            for record in self.campaign_history
        )

    def to_runtime_character(self) -> Character:
        max_hp = compute_max_hp(self.constitution)
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
            inventory=[item.model_copy() for item in self.inventory],
            skills=list(self.skills),
        )

    def format_career_context(self) -> str:
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
                }.get(record.status, record.status)
                summary = record.summary.strip() or "（尚无摘要）"
                lines.append(
                    f"- 《{record.scenario_title}》[{status_label}·{record.turn_count}回合] {summary}"
                )
        elif self.career_summary.strip():
            lines.append(f"生涯摘要：{self.career_summary.strip()}")
        if self.skills:
            lines.append(f"已掌握技能：{'、'.join(self.skills)}")
        if self.inventory:
            lines.append(
                f"持有物品：{'、'.join(item.display() for item in self.inventory)}"
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


def _rebuild_career_summary(card: CharacterCard) -> str:
    parts: list[str] = []
    for record in card.campaign_history:
        if not record.summary.strip():
            continue
        parts.append(f"《{record.scenario_title}》：{record.summary.strip()}")
    return " ".join(parts[-5:])


def prepare_card_for_new_campaign(card: CharacterCard, scenario: Scenario) -> None:
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

    merged_skills = list(card.skills)
    for skill in character.skills:
        if skill not in merged_skills:
            merged_skills.append(skill)
    card.skills = merged_skills
    card.inventory = [item.model_copy() for item in character.inventory]

    for fact in game_state.memory_facts:
        if fact not in card.notable_facts:
            card.notable_facts.append(fact)
    if len(card.notable_facts) > 30:
        card.notable_facts = card.notable_facts[-30:]

    record = _find_active_campaign(card, scenario.id)
    if record is None:
        record = CampaignRecord(
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            status="paused" if finalize else "active",
            last_played_at=_utc_now(),
        )
        card.campaign_history.append(record)
    record.scenario_title = scenario.title
    record.turn_count = game_state.turn_count
    record.last_played_at = _utc_now()
    if game_state.story_summary.strip():
        record.summary = game_state.story_summary.strip()
    if finalize:
        record.status = "paused"

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

    def list_character_cards(self, profile_id: str) -> list[CharacterCard]:
        cards_dir = self._characters_dir(profile_id)
        cards_dir.mkdir(parents=True, exist_ok=True)
        cards: list[CharacterCard] = []
        for path in cards_dir.glob("*.json"):
            try:
                cards.append(
                    CharacterCard.model_validate(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                )
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
        return CharacterCard.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def delete_character_card(self, profile_id: str, card_id: str) -> int:
        """删除角色卡及其关联存档（按 character_id）。返回删除的存档数量。"""
        save_manager = self.get_save_manager(profile_id)
        deleted_saves = save_manager.delete_by_character_id(card_id)
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
            except Exception:
                continue

        for legacy_path in legacy_files:
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
