
from game.results import ScenePatch, StatePatch
from game.turn_context import TurnContext
from game.turn_pipeline import _should_refresh_scene_map


def test_should_refresh_scene_map_on_scene_change():
    ctx = TurnContext(
        user_input="进入楼道",
        character=None,  # type: ignore[arg-type]
        game_state=None,  # type: ignore[arg-type]
        scenario=None,  # type: ignore[arg-type]
        history=[],
        world_patch=StatePatch(scene=ScenePatch(scene_id="floor-1-hall", scene_name="一楼楼道")),
    )
    assert _should_refresh_scene_map(ctx) is True


def test_should_refresh_scene_map_skips_opening():
    ctx = TurnContext(
        user_input="开始",
        character=None,  # type: ignore[arg-type]
        game_state=None,  # type: ignore[arg-type]
        scenario=None,  # type: ignore[arg-type]
        history=[],
        is_opening=True,
        world_patch=StatePatch(scene=ScenePatch(scene_id="entrance-gate", scene_name="门口")),
    )
    assert _should_refresh_scene_map(ctx) is False


def test_should_refresh_scene_map_on_map_discovery():
    ctx = TurnContext(
        user_input="查看楼层图",
        character=None,  # type: ignore[arg-type]
        game_state=None,  # type: ignore[arg-type]
        scenario=None,  # type: ignore[arg-type]
        history=[],
        world_patch=StatePatch(map_discovery=True),
    )
    assert _should_refresh_scene_map(ctx) is True
