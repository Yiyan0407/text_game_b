from unittest.mock import MagicMock, patch

from chain.character_portrait import build_portrait_prompt, generate_portrait_url
from chain.scene_image import ImageGenerationResult
from game.inventory import InventoryItem
from game.models import Character
from game.profile import CharacterCard, ProfileManager


def test_build_portrait_prompt_includes_background_and_world():
    card = CharacterCard.from_character(
        Character(name="艾拉", background="雾港来的老练调查员。"),
    )
    card.preferred_world_id = "coc"
    text = build_portrait_prompt(card)
    assert "艾拉" in text
    assert "写实" in text
    assert "雾港来的老练调查员" in text
    assert "克苏鲁" in text


def test_build_portrait_prompt_includes_inventory():
    card = CharacterCard.from_character(Character(name="测试"))
    card.inventory = [InventoryItem(name="古旧地图"), InventoryItem(name="银质护符")]
    text = build_portrait_prompt(card)
    assert "古旧地图" in text
    assert "银质护符" in text


def test_build_portrait_prompt_includes_career_hints():
    card = CharacterCard.from_character(Character(name="测试"))
    card.career_summary = "左脸有刀疤，常穿黑色风衣。"
    card.notable_facts = ["右眼义体发出微光"]
    text = build_portrait_prompt(card, world_id="cyberpunk")
    assert "刀疤" in text
    assert "义体" in text
    assert "赛博朋克" in text


@patch("chain.character_portrait.get_settings")
@patch("chain.character_portrait.generate_with_policy_fallback")
def test_generate_portrait_uses_seedream(mock_fallback, mock_settings):
    settings = MagicMock()
    settings.enable_character_portraits = True
    settings.image_provider = "seedream"
    mock_settings.return_value = settings
    mock_fallback.return_value = ImageGenerationResult(url="https://example.com/portrait.png")

    card = CharacterCard.from_character(Character(name="测试"))
    result = generate_portrait_url(card, world_id="fantasy")
    assert result.url == "https://example.com/portrait.png"
    mock_fallback.assert_called_once()


@patch("game.character_portrait.generate_portrait_url")
@patch("game.character_portrait._download_image")
def test_generate_and_save_portrait_persists_file(mock_download, mock_generate, tmp_path):
    from game.character_portrait import generate_and_save_portrait

    mock_generate.return_value = ImageGenerationResult(url="https://example.com/portrait.png")
    mock_download.return_value = (b"fake-image-bytes", "")

    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    profile = manager.create_profile("测试")
    card = CharacterCard.from_character(Character(name="测试侠"))

    result = generate_and_save_portrait(manager, profile.profile_id, card, world_id="fantasy")
    assert result.ok
    assert result.card.portrait_file == "portrait.png"
    path = manager.portrait_file_path(profile.profile_id, result.card)
    assert path is not None
    assert path.exists()
    assert path.read_bytes() == b"fake-image-bytes"


def test_delete_character_card_removes_portrait_assets(tmp_path):
    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    profile = manager.create_profile("测试")
    card = CharacterCard.from_character(Character(name="测试侠"))
    manager.save_portrait(profile.profile_id, card, b"img", filename="portrait.png")
    assets_dir = manager._character_assets_dir(profile.profile_id, card.card_id)
    assert assets_dir.exists()

    manager.delete_character_card(profile.profile_id, card.card_id)
    assert not assets_dir.exists()
    assert manager.list_character_cards(profile.profile_id) == []
