from game.models import GameState


def test_register_scene_image_appends_gallery():
    state = GameState(current_scene="灰港码头", turn_count=3)
    state.register_scene_image("灰港码头", "https://example.com/a.jpg")
    assert state.scene_image_url == "https://example.com/a.jpg"
    assert len(state.scene_image_gallery) == 1
    assert state.scene_image_gallery[0].scene_name == "灰港码头"
    assert state.scene_image_gallery[0].turn_count == 3


def test_register_scene_image_dedupes_same_url():
    state = GameState(turn_count=5)
    state.register_scene_image("地点 A", "https://example.com/a.jpg")
    state.register_scene_image("地点 A 更新", "https://example.com/a.jpg")
    assert len(state.scene_image_gallery) == 1
    assert state.scene_image_gallery[0].scene_name == "地点 A 更新"


def test_migrate_legacy_scene_image_url():
    state = GameState.model_validate(
        {
            "current_scene": "旧场景",
            "scene_image_url": "https://example.com/legacy.jpg",
            "turn_count": 2,
        }
    )
    assert len(state.scene_image_gallery) == 1
    assert state.scene_image_gallery[0].image_url == "https://example.com/legacy.jpg"
