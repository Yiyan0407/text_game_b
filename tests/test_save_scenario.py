import json

import pytest

from game.models import Character, ChatMessage, GameState, Quest
from game.save import SaveGame, SaveManager, get_action_suggestions
from game.scenario import Scenario
from game.scenario_loader import ScenarioNotFoundError, list_scenarios, load_scenario


def test_load_scenario():
    scenario = load_scenario("missing_fishermen")
    assert scenario.id == "missing_fishermen"
    assert scenario.title == "雾港失踪案"
    assert len(scenario.key_nodes) >= 3
    assert len(scenario.endings) >= 2
    assert len(scenario.initial_quests) == 1


def test_list_scenarios():
    scenarios = list_scenarios()
    assert len(scenarios) >= 1
    assert any(s.id == "missing_fishermen" for s in scenarios)


def test_scenario_not_found():
    with pytest.raises(ScenarioNotFoundError):
        load_scenario("nonexistent")


def test_scenario_format_for_prompt():
    scenario = load_scenario("missing_fishermen")
    text = scenario.format_for_prompt()
    assert "雾港失踪案" in text
    assert "关键节点" in text


def test_scenario_apply_to_game_state():
    scenario = load_scenario("missing_fishermen")
    state = GameState()
    scenario.apply_to_game_state(state)
    assert state.scenario_id == "missing_fishermen"
    assert state.scene_id == "tavern_seagull"
    assert len(state.active_quests) == 1


def test_save_roundtrip(tmp_path):
    manager = SaveManager(saves_dir=tmp_path)
    character = Character(name="艾拉")
    game_state = GameState(scenario_id="missing_fishermen", turn_count=5)
    messages = [
        ChatMessage(role="user", content="你好"),
        ChatMessage(role="assistant", content="欢迎"),
    ]
    save_game = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=character,
        game_state=game_state,
        messages=messages,
        save_id="test-save-1",
    )
    manager.save(save_game)
    loaded = manager.load("test-save-1")

    assert loaded.character.name == "艾拉"
    assert loaded.game_state.turn_count == 5
    assert len(loaded.messages) == 2
    assert manager.list_saves()[0].character_name == "艾拉"


def test_load_legacy_save_without_action_suggestions(tmp_path):
    manager = SaveManager(saves_dir=tmp_path)
    legacy = {
        "save_id": "legacy-save",
        "saved_at": "2026-01-01T00:00:00+00:00",
        "scenario_id": "midnight_archive",
        "scenario_title": "午夜档案",
        "character": Character(name="姜").model_dump(),
        "game_state": GameState(turn_count=2).model_dump(),
        "messages": [ChatMessage(role="user", content="行动").model_dump()],
    }
    path = tmp_path / "legacy-save.json"
    path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    loaded = manager.load("legacy-save")
    assert get_action_suggestions(loaded) == []


def test_save_action_suggestions_roundtrip(tmp_path):
    manager = SaveManager(saves_dir=tmp_path)
    save_game = SaveGame.create(
        scenario_id="midnight_archive",
        scenario_title="午夜档案",
        character=Character(name="姜"),
        game_state=GameState(),
        messages=[ChatMessage(role="assistant", content="KP 叙事")],
        save_id="suggest-save",
        action_suggestions=["查官网", "联系内线", "分析压缩包"],
    )
    manager.save(save_game)
    loaded = manager.load("suggest-save")
    assert get_action_suggestions(loaded) == ["查官网", "联系内线", "分析压缩包"]


def test_save_delete(tmp_path):
    manager = SaveManager(saves_dir=tmp_path)
    save_game = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=Character(name="测试"),
        game_state=GameState(),
        messages=[],
        save_id="del-me",
    )
    manager.save(save_game)
    assert len(manager.list_saves()) == 1
    manager.delete("del-me")
    assert len(manager.list_saves()) == 0


def test_save_create_rebuilds_nested_models(tmp_path):
    """SaveGame.create 应能通过 model_dump 重建嵌套模型（兼容 Streamlit 热重载）。"""
    manager = SaveManager(saves_dir=tmp_path)
    character = Character(name="姜", constitution=14, wisdom=10)
    game_state = GameState(turn_count=3, current_scene="测试场景")
    messages = [ChatMessage(role="user", content="行动")]

    save_game = SaveGame.create(
        scenario_id="midnight_archive",
        scenario_title="午夜档案",
        character=Character.model_validate(character.model_dump()),
        game_state=GameState.model_validate(game_state.model_dump()),
        messages=[ChatMessage.model_validate(m.model_dump()) for m in messages],
        save_id="rebuild-save",
    )
    manager.save(save_game)
    loaded = manager.load("rebuild-save")
    assert loaded.character.name == "姜"
    assert loaded.character.constitution == 14
    assert loaded.game_state.turn_count == 3
