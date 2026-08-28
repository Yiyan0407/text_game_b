import json

import pytest

from game.models import Character, ChatMessage, GameState
from game.save import SaveGame, SaveManager
from game.session import apply_save_to_session, reload_current_save_from_disk
from game.scenario import Scenario


class FakeSessionState:
    def __init__(self, initial=None):
        self._data = dict(initial or {})

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        if key == "_data":
            super().__setattr__(key, value)
        else:
            self._data[key] = value


@pytest.fixture
def save_setup(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    (scenarios_dir / "missing_fishermen.json").write_text(
        json.dumps(
            {
                "id": "missing_fishermen",
                "title": "雾港失踪案",
                "world_id": "fantasy",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("config.settings.SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr("game.scenario_loader.SCENARIOS_DIR", scenarios_dir)
    return tmp_path / "saves"


def test_reload_current_save_from_disk_picks_up_new_messages(save_setup):
    save_manager = SaveManager(saves_dir=save_setup, profile_id="p1")
    character = Character(name="艾拉", background="斥候")
    game_state = GameState(turn_count=1, current_scene="酒馆")
    messages = [ChatMessage(role="assistant", content="开场白")]
    save_game = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=character,
        game_state=game_state,
        messages=messages,
        profile_id="p1",
    )
    save_manager.save(save_game)

    state = {
        "save_manager": save_manager,
        "current_save_id": save_game.save_id,
        "messages": list(messages),
        "game_state": game_state,
        "character": character,
    }

    fake = FakeSessionState(state)
    import game.session as session_module

    original = session_module.st.session_state
    session_module.st.session_state = fake
    try:
        result = reload_current_save_from_disk()
        assert result.success
        assert result.already_latest

        updated = SaveGame.create(
            scenario_id="missing_fishermen",
            scenario_title="雾港失踪案",
            character=character,
            game_state=GameState(turn_count=2, current_scene="码头"),
            messages=[
                *messages,
                ChatMessage(role="user", content="去码头"),
                ChatMessage(role="assistant", content="你来到码头。"),
            ],
            save_id=save_game.save_id,
            profile_id="p1",
        )
        save_manager.save(updated)

        result = reload_current_save_from_disk()
        assert result.success
        assert result.new_messages == 2
        assert len(fake.messages) == 3
        assert fake.game_state.turn_count == 2
        assert fake.game_state.current_scene == "码头"
    finally:
        session_module.st.session_state = original


def test_apply_save_to_session_updates_world_id():
    scenario = Scenario(id="missing_fishermen", title="雾港失踪案", world_id="fantasy")
    save_game = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=Character(name="艾拉"),
        game_state=GameState(),
        messages=[],
        world_id="modern",
    )

    import game.session as session_module

    fake = FakeSessionState()
    original = session_module.st.session_state
    session_module.st.session_state = fake
    try:
        apply_save_to_session(save_game, scenario)
        assert fake.scenario.world_id == "modern"
        assert fake.game_started is True
    finally:
        session_module.st.session_state = original
