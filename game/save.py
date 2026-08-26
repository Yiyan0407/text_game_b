import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from config.settings import SAVES_DIR
from game.models import Character, ChatMessage, GameState


def _normalize_save_payload(raw: dict) -> dict:
    """补全旧版存档缺少的字段。"""
    payload = dict(raw)
    payload.setdefault("action_suggestions", [])
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
    ) -> "SaveGame":
        return cls(
            save_id=save_id or str(uuid.uuid4()),
            saved_at=datetime.now(timezone.utc).isoformat(),
            scenario_id=scenario_id,
            scenario_title=scenario_title,
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
    def __init__(self, saves_dir: Path | None = None):
        self.saves_dir = saves_dir or SAVES_DIR
        self.saves_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, save_id: str) -> Path:
        return self.saves_dir / f"{save_id}.json"

    def save(self, save_game: SaveGame) -> Path:
        save_game.saved_at = datetime.now(timezone.utc).isoformat()
        path = self._path(save_game.save_id)
        path.write_text(
            save_game.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path

    def load(self, save_id: str) -> SaveGame:
        path = self._path(save_id)
        if not path.exists():
            raise FileNotFoundError(f"存档不存在: {save_id}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        return SaveGame.model_validate(_normalize_save_payload(raw))

    def delete(self, save_id: str) -> None:
        path = self._path(save_id)
        if path.exists():
            path.unlink()

    def list_saves(self) -> list[SaveMeta]:
        saves: list[SaveMeta] = []
        for path in self.saves_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                data = SaveGame.model_validate(_normalize_save_payload(raw))
            except Exception:
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
