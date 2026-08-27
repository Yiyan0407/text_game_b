import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from config.settings import SAVES_DIR
from game.models import Character, ChatMessage, GameState

logger = logging.getLogger(__name__)


def _normalize_save_payload(raw: dict) -> dict:
    """补全旧版存档缺少的字段。"""
    payload = dict(raw)
    payload.setdefault("action_suggestions", [])
    payload.setdefault("profile_id", "")
    payload.setdefault("character_id", "")
    payload.setdefault("world_id", "")
    return payload


def get_action_suggestions(save_game: "SaveGame") -> list[str]:
    """读取行动建议，兼容旧存档与 Streamlit 热重载后的模型实例。"""
    data = save_game.model_dump()
    suggestions = data.get("action_suggestions")
    if not suggestions:
        return []
    return list(suggestions)


def _fresh_model(model_cls: type[BaseModel], value: BaseModel | dict) -> BaseModel:
    """通过 dict 重建模型，避免 Streamlit 热重载后类引用不一致导致校验失败。"""
    if isinstance(value, BaseModel):
        return model_cls.model_validate(value.model_dump())
    return model_cls.model_validate(value)


class SaveGame(BaseModel):
    save_id: str
    saved_at: str
    scenario_id: str
    scenario_title: str
    profile_id: str = ""
    character_id: str = ""
    world_id: str = ""
    character: Character
    game_state: GameState
    messages: list[ChatMessage] = Field(default_factory=list)
    action_suggestions: list[str] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        scenario_id: str,
        scenario_title: str,
        character: Character,
        game_state: GameState,
        messages: list[ChatMessage],
        save_id: str | None = None,
        action_suggestions: list[str] | None = None,
        profile_id: str = "",
        character_id: str = "",
        world_id: str = "",
    ) -> "SaveGame":
        return cls(
            save_id=save_id or str(uuid.uuid4()),
            saved_at=datetime.now(timezone.utc).isoformat(),
            scenario_id=scenario_id,
            scenario_title=scenario_title,
            profile_id=profile_id,
            character_id=character_id,
            world_id=world_id,
            character=_fresh_model(Character, character),
            game_state=_fresh_model(GameState, game_state),
            messages=[_fresh_model(ChatMessage, msg) for msg in messages],
            action_suggestions=list(action_suggestions or []),
        )


class SaveMeta(BaseModel):
    save_id: str
    saved_at: str
    scenario_id: str
    scenario_title: str
    character_name: str
    turn_count: int
    current_scene: str


class SaveManager:
    def __init__(self, saves_dir: Path | None = None, profile_id: str = ""):
        self.saves_dir = saves_dir or SAVES_DIR
        self.profile_id = profile_id
        self.saves_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, save_id: str) -> Path:
        return self.saves_dir / f"{save_id}.json"

    def save(self, save_game: SaveGame) -> Path:
        save_game.saved_at = datetime.now(timezone.utc).isoformat()
        if self.profile_id and not save_game.profile_id:
            save_game.profile_id = self.profile_id
        path = self._path(save_game.save_id)
        content = save_game.model_dump_json(indent=2)
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=self.saves_dir,
                prefix=f".{save_game.save_id}-",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            tmp_path = None
        except Exception:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise
        return path

    def load(self, save_id: str) -> SaveGame:
        path = self._path(save_id)
        if not path.exists():
            raise FileNotFoundError(f"存档不存在: {save_id}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        data = SaveGame.model_validate(_normalize_save_payload(raw))
        return SaveGame(
            save_id=data.save_id,
            saved_at=data.saved_at,
            scenario_id=data.scenario_id,
            scenario_title=data.scenario_title,
            profile_id=data.profile_id,
            character_id=data.character_id,
            world_id=data.world_id,
            character=_fresh_model(Character, data.character),
            game_state=_fresh_model(GameState, data.game_state),
            messages=[_fresh_model(ChatMessage, msg) for msg in data.messages],
            action_suggestions=list(data.action_suggestions),
        )

    def delete(self, save_id: str) -> None:
        path = self._path(save_id)
        if path.exists():
            path.unlink()

    def list_save_ids_for_character(self, character_id: str) -> list[str]:
        if not character_id:
            return []
        save_ids: list[str] = []
        for path in self.saves_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                payload = _normalize_save_payload(raw)
                if payload.get("character_id") == character_id:
                    save_ids.append(str(payload.get("save_id", path.stem)))
            except Exception as exc:
                logger.warning("跳过损坏的存档 %s: %s", path.name, exc)
                continue
        return save_ids

    def delete_by_character_id(self, character_id: str) -> int:
        save_ids = self.list_save_ids_for_character(character_id)
        for save_id in save_ids:
            self.delete(save_id)
        return len(save_ids)

    def list_saves(self) -> list[SaveMeta]:
        saves: list[SaveMeta] = []
        for path in self.saves_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                data = SaveGame.model_validate(_normalize_save_payload(raw))
            except Exception as exc:
                logger.warning("跳过损坏的存档 %s: %s", path.name, exc)
                continue
            saves.append(
                SaveMeta(
                    save_id=data.save_id,
                    saved_at=data.saved_at,
                    scenario_id=data.scenario_id,
                    scenario_title=data.scenario_title,
                    character_name=data.character.name,
                    turn_count=data.game_state.turn_count,
                    current_scene=data.game_state.current_scene,
                )
            )
        saves.sort(key=lambda s: s.saved_at, reverse=True)
        return saves

    def get_latest(self) -> SaveGame | None:
        saves = self.list_saves()
        if not saves:
            return None
        return self.load(saves[0].save_id)
