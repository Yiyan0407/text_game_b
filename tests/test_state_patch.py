from game.inventory import InventoryItem
from game.models import Character, GameState
from game.results import ActionRouteResult, InventoryPatch, NpcPatch, StatePatch
from game.state_patch import apply_inventory_change, apply_state_patch, patch_from_dict


def test_apply_inventory_change_add():
    character = Character(name="测试")
    result = apply_inventory_change(
        character,
        InventoryPatch(action="add", item="火把", quantity=1, unit="个"),
    )
    assert "获得" in result
    assert character.has_inventory_item("火把")


def test_apply_inventory_change_blocks_delivered_duplicate():
    character = Character(name="测试")
    delivered = frozenset({"止血凝胶"})
    apply_inventory_change(
        character,
        InventoryPatch(action="add", item="止血凝胶", quantity=3, unit="瓶"),
        delivered_items=delivered,
    )
    result = apply_inventory_change(
        character,
        InventoryPatch(action="add", item="止血凝胶", quantity=3, unit="瓶"),
        delivered_items=delivered,
    )
    assert "跳过重复添加" in result
    assert not character.has_inventory_item("止血凝胶")


def test_apply_state_patch_npc():
    character = Character(name="测试")
    game_state = GameState()
    patch = StatePatch(
        npcs=[NpcPatch(name="老约翰", attitude="unknown", notes="失踪渔民")]
    )
    events = apply_state_patch(patch, character, game_state)
    assert any("老约翰" in event for event in events)
    assert any(npc.name == "老约翰" for npc in game_state.npcs)


def test_apply_state_patch_blocks_purchase_duplicate():
    character = Character(name="测试")
    game_state = GameState()
    route = ActionRouteResult(
        approved=True,
        item_usage="purchase",
        referenced_items=["短剑"],
    )
    mechanical = ["获得：短剑"]
    patch = StatePatch(
        inventory=[InventoryPatch(action="add", item="短剑", quantity=1)]
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        delivered_items=frozenset({"短剑"}),
        mechanical_events=mechanical,
    )
    assert any("跳过重复添加" in event for event in events)


def test_apply_state_patch_blocks_skill_on_failed_roll():
    character = Character(name="测试")
    game_state = GameState()
    patch = StatePatch(
        skills=[{"action": "add", "skill": "潜行", "description": "隐蔽"}]  # type: ignore
    )
    # use proper SkillPatch via patch_from_dict
    patch = patch_from_dict(
        {"skills": [{"action": "add", "skill": "潜行", "description": "隐蔽"}]}
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        mechanical_events=["敏捷检定 d20=5 vs DC14 → 失败 ✗"],
    )
    assert any("跳过技能添加" in event for event in events)
    assert not character.has_skill("潜行")


def test_apply_state_patch_blocks_scene_change_in_combat():
    from game.models import CombatState

    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(active=True)
    from game.results import ScenePatch

    patch = StatePatch(scene=ScenePatch(scene_id="x", scene_name="别处"))
    events = apply_state_patch(patch, character, game_state)
    assert any("跳过场景变更" in event for event in events)


def test_patch_from_dict_empty():
    patch = patch_from_dict({})
    assert patch.npcs == []
    assert patch.end_combat is False
