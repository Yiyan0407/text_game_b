from game.game_config import GameConfig, apply_guidance_hint, default_game_config
from game.save import SaveGame, SaveManager
from game.models import Character, GameState


def test_default_game_config():
    config = default_game_config()
    assert config.kp_guidance == "balanced"
    assert config.enable_background_validation is True


def test_apply_guidance_hint_balanced_early_turn():
    config = GameConfig(kp_guidance="balanced")
    result = apply_guidance_hint("观察四周", 1, config)
    assert "[KP 引导" in result


def test_apply_guidance_hint_freeform_skips_early_turn():
    config = GameConfig(kp_guidance="freeform")
    result = apply_guidance_hint("观察四周", 1, config)
    assert result == "观察四周"


def test_apply_guidance_hint_freeform_on_confusion():
    config = GameConfig(kp_guidance="freeform")
    result = apply_guidance_hint("接下来怎么办", 10, config)
    assert "[KP 引导" in result


def test_apply_guidance_hint_script_guided_longer_window():
    config = GameConfig(kp_guidance="script_guided")
    result = apply_guidance_hint("观察四周", 5, config)
    assert "key_nodes" in result


def test_apply_guidance_hint_script_guided_pending_beats_every_turn():
    from game.models import ScenarioProgress
    from game.scenario import Scenario, ScenarioNode

    scenario = Scenario(
        id="s",
        title="t",
        key_nodes=[ScenarioNode(id="n", title="节点", beats=["某要素"])],
    )
    config = GameConfig(kp_guidance="script_guided")
    result = apply_guidance_hint(
        "沿楼梯向下",
        20,
        config,
        scenario=scenario,
        progress=ScenarioProgress(),
    )
    assert "待完成要素" in result


def test_save_roundtrip_game_config(tmp_path):
    manager = SaveManager(saves_dir=tmp_path)
    config = GameConfig(kp_guidance="script_guided", enable_background_validation=False)
    save_game = SaveGame.create(
        scenario_id="test",
        scenario_title="测试",
        character=Character(name="测试"),
        game_state=GameState(),
        messages=[],
        game_config=config,
    )
    manager.save(save_game)
    loaded = manager.load(save_game.save_id)
    assert loaded.game_config.kp_guidance == "script_guided"
    assert loaded.game_config.enable_background_validation is False
