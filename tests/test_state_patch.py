from game.inventory import InventoryItem
from game.models import Character, GameState
from game.results import ActionRouteResult, EquipmentPatch, InventoryPatch, NpcPatch, StatePatch
from game.state_patch import apply_inventory_change, apply_state_patch, patch_from_dict


def test_apply_inventory_change_add():
    character = Character(name="测试")
    result = apply_inventory_change(
        character,
        InventoryPatch(action="add", item="火把", quantity=1, unit="个"),
    )
    assert "获得" in result
    assert character.has_inventory_item("火把")


def test_apply_inventory_change_respects_explicit_kind():
    character = Character(name="测试")
    apply_inventory_change(
        character,
        InventoryPatch(
            action="add",
            item="定金币",
            quantity=15,
            unit="枚",
            kind="document",
        ),
    )
    item = character.find_inventory_item("定金币")
    assert item is not None
    assert item.kind == "document"


def test_patch_from_dict_coerces_kind():
    patch = patch_from_dict(
        {
            "inventory": [
                {
                    "action": "add",
                    "item": "压缩饼干",
                    "quantity": 3,
                    "unit": "包",
                    "kind": "consumable",
                }
            ]
        }
    )
    assert patch.inventory[0].kind == "consumable"


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


def test_item_sync_allows_add_when_route_is_pickup_but_not_mechanically_granted():
    """KP 叙事后 ItemSync：NPC 交付不应被 pickup 路由误拦。"""
    character = Character(name="测试")
    game_state = GameState()
    route = ActionRouteResult(
        approved=True,
        item_usage="pickup",
        referenced_items=["量子纠缠通信器"],
    )
    patch = StatePatch(
        inventory=[
            InventoryPatch(
                action="add",
                item="量子纠缠通信器",
                quantity=1,
                unit="枚",
                kind="durable",
                description="已植入耳后接口",
            ),
        ],
        equipment=[
            EquipmentPatch(action="equip", item="量子纠缠通信器", slot="body"),
        ],
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=["获得：病毒分析仪", "获得：分子切割器"],
        inventory_sync=True,
    )
    assert character.has_inventory_item("量子纠缠通信器")
    assert character.is_item_equipped("量子纠缠通信器")
    assert any("获得" in event for event in events)


def test_world_state_still_blocks_pickup_without_mechanical_grant():
    character = Character(name="测试")
    game_state = GameState()
    route = ActionRouteResult(
        approved=True,
        item_usage="pickup",
        referenced_items=["量子纠缠通信器"],
    )
    patch = StatePatch(
        inventory=[
            InventoryPatch(action="add", item="量子纠缠通信器", quantity=1, unit="枚"),
        ],
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=[],
        inventory_sync=False,
    )
    assert not character.has_inventory_item("量子纠缠通信器")
    assert any("拾取未成功" in event for event in events)


def test_apply_state_patch_blocks_exploration_duplicate_pickup():
    character = Character(name="测试")
    game_state = GameState()
    route = ActionRouteResult(
        approved=True,
        item_usage="pickup",
        referenced_items=["药瓶"],
    )
    patch = patch_from_dict(
        {"inventory": [{"action": "add", "item": "药瓶", "quantity": 1, "unit": "个"}]}
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=["获得：药瓶"],
    )
    assert any("机械层已结算" in event for event in events)
    assert not character.has_inventory_item("药瓶")


def test_apply_state_patch_blocks_duplicate_remove_after_use():
    character = Character(name="测试", inventory=["治疗药水"])
    game_state = GameState()
    route = ActionRouteResult(
        approved=True,
        item_usage="use",
        referenced_items=["治疗药水"],
    )
    patch = patch_from_dict(
        {"inventory": [{"action": "remove", "item": "治疗药水", "quantity": 1}]}
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=["使用：治疗药水（背包移除：治疗药水）"],
    )
    assert any("跳过重复移除" in event for event in events)
    assert character.has_inventory_item("治疗药水")


def test_resolve_mechanics_pickup_roll_failure_does_not_grant_items():
    from game.orchestrator import GameOrchestrator

    orchestrator = GameOrchestrator()
    character = Character(name="测试", dexterity=8)
    game_state = GameState()
    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="dex",
        dc=25,
        item_usage="pickup",
        referenced_items=["钱包"],
        action_intent="趁乱偷钱包",
    )
    events = orchestrator._resolve_mechanics(route, character, game_state, None)
    assert not any(event.startswith("获得：") for event in events)
    assert not character.has_inventory_item("钱包")
