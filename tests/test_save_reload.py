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
        "last_loaded_save_at": save_game.saved_at,
    }

    fake = FakeSessionState(state)
    import game.session as session_module

    original = session_module.st.session_state
    session_module.st.session_state = fake
    try:
        result = reload_current_save_from_disk()
        assert result.success
        assert result.already_latest
        assert fake.last_loaded_save_at == save_game.saved_at

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
        assert fake.last_loaded_save_at == updated.saved_at
    finally:
        session_module.st.session_state = original


def test_reload_detects_hp_change_with_same_message_count(save_setup):
    save_manager = SaveManager(saves_dir=save_setup, profile_id="p1")
    character = Character(name="艾拉", hp=20, max_hp=20)
    game_state = GameState(turn_count=2, current_scene="战斗")
    messages = [ChatMessage(role="assistant", content="开战")]
    save_game = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=character,
        game_state=game_state,
        messages=messages,
        profile_id="p1",
    )
    save_manager.save(save_game)

    stale_character = character.model_copy(deep=True)
    stale_state = game_state.model_copy(deep=True)
    fake = FakeSessionState(
        {
            "save_manager": save_manager,
            "current_save_id": save_game.save_id,
            "messages": list(messages),
            "game_state": stale_state,
            "character": stale_character,
            "last_loaded_save_at": save_game.saved_at,
        }
    )
    import game.session as session_module

    original = session_module.st.session_state
    session_module.st.session_state = fake
    try:
        wounded = character.model_copy(update={"hp": 8})
        updated = SaveGame.create(
            scenario_id="missing_fishermen",
            scenario_title="雾港失踪案",
            character=wounded,
            game_state=game_state,
            messages=messages,
            save_id=save_game.save_id,
            profile_id="p1",
        )
        save_manager.save(updated)

        result = reload_current_save_from_disk()
        assert result.success
        assert not result.already_latest
        assert fake.character.hp == 8
    finally:
        session_module.st.session_state = original


def test_apply_save_to_session_syncs_character_card(tmp_path):
    from game.profile import CharacterCard, ProfileManager

    profiles_dir = tmp_path / "profiles"
    manager = ProfileManager(profiles_dir=profiles_dir)
    profile = manager.create_profile("测试档案")
    card = CharacterCard.from_character(Character(name="艾拉", inventory=["旧剑"]))
    manager.save_character_card(profile.profile_id, card)

    save_game = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=Character(name="艾拉", inventory=["破禁符"]),
        game_state=GameState(turn_count=4),
        messages=[],
        profile_id=profile.profile_id,
        character_id=card.card_id,
    )
    scenario = Scenario(id="missing_fishermen", title="雾港失踪案", world_id="fantasy")

    import game.session as session_module

    fake = FakeSessionState(
        {
            "current_profile_id": profile.profile_id,
            "current_character_id": card.card_id,
            "profile_manager": manager,
        }
    )
    original = session_module.st.session_state
    session_module.st.session_state = fake
    try:
        apply_save_to_session(save_game, scenario)
        reloaded = manager.load_character_card(profile.profile_id, card.card_id)
        assert any(item.name == "破禁符" for item in reloaded.inventory)
    finally:
        session_module.st.session_state = original


def test_save_accepts_zero_hp(save_setup):
    character = Character(name="艾拉", hp=0, max_hp=20)
    save_game = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=character,
        game_state=GameState(turn_count=3, current_scene="竞技场"),
        messages=[],
    )
    assert save_game.character.hp == 0
    SaveManager(saves_dir=save_setup).save(save_game)


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
