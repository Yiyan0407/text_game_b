import json

import pytest

from game.inventory import InventoryItem
from game.models import Character, ChatMessage, GameState
from game.skills import Skill
from game.profile import CharacterCard, ProfileManager, CharacterLoadout
from game.save import SaveGame, SaveManager


def test_create_profile_and_isolated_saves(tmp_path):
    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    alice = manager.create_profile("Alice")
    bob = manager.create_profile("Bob")

    alice_saves = manager.get_save_manager(alice.profile_id)
    bob_saves = manager.get_save_manager(bob.profile_id)

    alice_saves.save(
        SaveGame.create(
            scenario_id="missing_fishermen",
            scenario_title="雾港失踪案",
            character=Character(name="艾拉"),
            game_state=GameState(turn_count=1),
            messages=[],
            save_id="alice-save",
            profile_id=alice.profile_id,
        )
    )
    bob_saves.save(
        SaveGame.create(
            scenario_id="midnight_archive",
            scenario_title="午夜档案",
            character=Character(name="姜"),
            game_state=GameState(turn_count=2),
            messages=[],
            save_id="bob-save",
            profile_id=bob.profile_id,
        )
    )

    assert len(alice_saves.list_saves()) == 1
    assert len(bob_saves.list_saves()) == 1
    assert alice_saves.list_saves()[0].character_name == "艾拉"
    assert bob_saves.list_saves()[0].character_name == "姜"


def test_character_card_roundtrip_and_runtime_reset(tmp_path):
    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    profile = manager.create_profile("测试档案")
    card = CharacterCard.from_character(
        Character(
            name="李逍遥",
            background="蜀山弟子",
            strength=14,
            inventory=["旧剑"],
            skills=["御剑术"],
        ),
        preferred_world_id="xianxia",
    )
    manager.save_character_card(profile.profile_id, card)
    loaded = manager.load_character_card(profile.profile_id, card.card_id)
    loadout = card.library_loadout()
    runtime = loaded.to_runtime_character(loadout)

    assert loaded.name == "李逍遥"
    assert runtime.strength == 14
    assert runtime.inventory == [InventoryItem(name="旧剑", quantity=1, unit="个")]
    assert runtime.skills == [Skill(name="御剑术")]
    assert runtime.hp == runtime.max_hp


def test_sync_card_from_adventure_updates_career(tmp_path):
    from game.profile import sync_card_from_adventure
    from game.scenario import Scenario

    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    profile = manager.create_profile("测试")
    card = CharacterCard.from_character(Character(name="测试侠"))
    manager.save_character_card(profile.profile_id, card)

    character = Character(
        name="测试侠",
        inventory=["破禁符"],
        skills=["基础剑术"],
    )
    game_state = GameState(
        turn_count=12,
        story_summary="在坊市购得破禁符，得知秘境将开。",
        memory_facts=["与沈渊结盟"],
    )
    scenario = Scenario(id="test_mod", title="断剑峰秘境", world_id="xianxia")

    sync_card_from_adventure(card, character, game_state, scenario)
    manager.save_character_card(profile.profile_id, card)
    loaded = manager.load_character_card(profile.profile_id, card.card_id)

    assert loaded.inventory == [InventoryItem(name="破禁符", quantity=1, unit="个")]
    assert loaded.skills == [Skill(name="基础剑术")]
    assert loaded.notable_facts == ["与沈渊结盟"]
    assert len(loaded.campaign_history) == 1
    assert loaded.campaign_history[0].summary == game_state.story_summary
    assert "断剑峰秘境" in loaded.format_career_context()


def test_format_career_context_skips_empty_new_campaign():
    from game.profile import CampaignRecord

    card = CharacterCard.from_character(Character(name="新人"))
    card.campaign_history.append(
        CampaignRecord(
            scenario_id="new_mod",
            scenario_title="新模组",
            status="active",
        )
    )
    assert card.format_career_context() == ""


def test_migrate_legacy_saves_keeps_corrupt_files(tmp_path):
    legacy_dir = tmp_path / "legacy_saves"
    legacy_dir.mkdir()
    (legacy_dir / "bad.json").write_text("{not json", encoding="utf-8")
    good_payload = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=Character(name="旧角色"),
        game_state=GameState(turn_count=3),
        messages=[ChatMessage(role="user", content="测试")],
        save_id="legacy-1",
    ).model_dump()
    (legacy_dir / "legacy-1.json").write_text(
        json.dumps(good_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    import game.profile as profile_module

    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    original_saves = profile_module.SAVES_DIR
    profile_module.SAVES_DIR = legacy_dir
    try:
        migrated = manager.migrate_legacy_saves()
    finally:
        profile_module.SAVES_DIR = original_saves

    assert migrated is not None
    assert (legacy_dir / "bad.json").exists()
    assert not (legacy_dir / "legacy-1.json").exists()


def test_migrate_legacy_saves(tmp_path):
    legacy_dir = tmp_path / "legacy_saves"
    legacy_dir.mkdir()
    legacy_payload = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=Character(name="旧角色"),
        game_state=GameState(turn_count=3),
        messages=[ChatMessage(role="user", content="测试")],
        save_id="legacy-1",
    ).model_dump()
    (legacy_dir / "legacy-1.json").write_text(
        json.dumps(legacy_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    from config.settings import SAVES_DIR as real_saves

    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    import game.profile as profile_module

    original_saves = profile_module.SAVES_DIR
    profile_module.SAVES_DIR = legacy_dir
    try:
        migrated = manager.migrate_legacy_saves()
    finally:
        profile_module.SAVES_DIR = original_saves

    assert migrated is not None
    saves = manager.get_save_manager(migrated.profile_id).list_saves()
    assert len(saves) == 1
    assert saves[0].character_name == "旧角色"
    cards = manager.list_character_cards(migrated.profile_id)
    assert len(cards) == 1
    assert cards[0].name == "旧角色"


def test_delete_profile_removes_all_data(tmp_path):
    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    profile = manager.create_profile("待删除")
    card = CharacterCard.from_character(Character(name="测试"))
    manager.save_character_card(profile.profile_id, card)
    manager.get_save_manager(profile.profile_id).save(
        SaveGame.create(
            scenario_id="missing_fishermen",
            scenario_title="雾港失踪案",
            character=Character(name="测试"),
            game_state=GameState(),
            messages=[],
            save_id="save-1",
            profile_id=profile.profile_id,
        )
    )
    manager.delete_profile(profile.profile_id)
    assert manager.list_profiles() == []
    assert manager.list_character_cards(profile.profile_id) == []
    assert manager.get_save_manager(profile.profile_id).list_saves() == []


def test_sync_card_marks_deceased_on_death(tmp_path):
    from game.profile import CampaignRecord, sync_card_from_adventure
    from game.scenario import Scenario

    card = CharacterCard.from_character(Character(name="艾拉"))
    character = Character(name="艾拉", hp=0, max_hp=20)
    game_state = GameState(turn_count=12, story_summary="在竞技场中被长矛刺穿。")
    scenario = Scenario(id="arena", title="试炼竞技场", world_id="fantasy")
    card.campaign_history.append(
        CampaignRecord(
            scenario_id="arena",
            scenario_title="试炼竞技场",
            status="active",
        )
    )

    sync_card_from_adventure(card, character, game_state, scenario)
    sync_card_from_adventure(card, character, game_state, scenario)

    assert card.deceased is True
    assert card.death_note
    failed = [r for r in card.campaign_history if r.scenario_id == "arena" and r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].turn_count == 12
    assert card.is_playable() is False


def test_consolidate_campaign_history_merges_duplicate_failed():
    from game.profile import CampaignRecord, _consolidate_campaign_history

    card = CharacterCard.from_character(Character(name="艾拉"))
    card.campaign_history = [
        CampaignRecord(scenario_id="arena", scenario_title="陨神竞技场", status="failed", turn_count=2),
        CampaignRecord(scenario_id="arena", scenario_title="陨神竞技场", status="failed", turn_count=2),
        CampaignRecord(scenario_id="arena", scenario_title="陨神竞技场", status="failed", turn_count=2),
    ]
    _consolidate_campaign_history(card)
    assert len(card.campaign_history) == 1
    assert card.campaign_history[0].status == "failed"


def test_prepare_card_rejects_deceased(tmp_path):
    from game.profile import prepare_card_for_new_campaign
    from game.scenario import Scenario

    card = CharacterCard.from_character(Character(name="艾拉"))
    card.deceased = True
    scenario = Scenario(id="arena", title="试炼竞技场", world_id="fantasy")

    import pytest

    with pytest.raises(ValueError, match="已死亡"):
        prepare_card_for_new_campaign(card, scenario)


def test_sync_merges_inventory_into_library():
    from game.profile import sync_card_from_adventure
    from game.scenario import Scenario

    card = CharacterCard.from_character(Character(name="测试", inventory=["旧剑"]))
    character = Character(name="测试", inventory=["新符"])
    game_state = GameState(turn_count=3)
    scenario = Scenario(id="mod", title="测试模组", world_id="fantasy")

    sync_card_from_adventure(card, character, game_state, scenario)

    names = {item.name for item in card.inventory}
    assert names == {"旧剑", "新符"}


def test_loadout_only_carries_selected_items():
    card = CharacterCard.from_character(
        Character(name="测试", inventory=["旧剑", "新符"], skills=["剑术", "潜行"])
    )
    loadout = CharacterLoadout(skill_names=["剑术"], item_names=["旧剑"])
    runtime = card.to_runtime_character(loadout)
    assert [skill.name for skill in runtime.skills] == ["剑术"]
    assert [item.name for item in runtime.inventory] == ["旧剑"]


def test_delete_character_card_also_deletes_linked_saves(tmp_path):
    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    profile = manager.create_profile("测试")
    card = CharacterCard.from_character(Character(name="测试侠"))
    manager.save_character_card(profile.profile_id, card)
    save_manager = manager.get_save_manager(profile.profile_id)
    for idx in range(2):
        save_manager.save(
            SaveGame.create(
                scenario_id="missing_fishermen",
                scenario_title="雾港失踪案",
                character=card.to_runtime_character(card.library_loadout()),
                game_state=GameState(turn_count=idx + 1),
                messages=[],
                save_id=f"save-{idx}",
                profile_id=profile.profile_id,
                character_id=card.card_id,
            )
        )
    assert len(save_manager.list_saves()) == 2

    deleted = manager.delete_character_card(profile.profile_id, card.card_id)
    assert deleted == 2
    assert manager.list_character_cards(profile.profile_id) == []
    assert save_manager.list_saves() == []


def test_save_includes_profile_and_character_ids(tmp_path):
    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    profile = manager.create_profile("玩家A")
    card = CharacterCard.from_character(Character(name="测试"))
    manager.save_character_card(profile.profile_id, card)
    save_manager = manager.get_save_manager(profile.profile_id)
    save_game = SaveGame.create(
        scenario_id="missing_fishermen",
        scenario_title="雾港失踪案",
        character=card.to_runtime_character(),
        game_state=GameState(),
        messages=[],
        save_id="linked-save",
        profile_id=profile.profile_id,
        character_id=card.card_id,
        world_id="fantasy",
    )
    save_manager.save(save_game)
    loaded = save_manager.load("linked-save")
    assert loaded.profile_id == profile.profile_id
    assert loaded.character_id == card.card_id
    assert loaded.world_id == "fantasy"
