from game.models import Character, GameState
from game.post_kp_mechanics import resolve_post_kp_mechanics
from game.results import ActionRouteResult, EquipmentPatch, InventoryPatch, StatePatch
from game.state_patch import apply_state_patch


def test_exploration_pickup_grants_item_before_item_sync_equip():
    character = Character(name="测试")
    game_state = GameState()
    route = ActionRouteResult(
        approved=True,
        item_usage="pickup",
        referenced_items=["撬棍"],
    )

    events = resolve_post_kp_mechanics(route, character, game_state)
    assert any("获得" in event and "撬棍" in event for event in events)
    assert character.has_inventory_item("撬棍")

    sync_events = apply_state_patch(
        StatePatch(
            inventory=[
                InventoryPatch(
                    action="add",
                    item="撬棍",
                    quantity=1,
                    unit="根",
                    kind="durable",
                    description="NPC 交付的撬棍，铁管缠布握把",
                )
            ],
            equipment=[EquipmentPatch(action="equip", item="撬棍", slot="hand")],
        ),
        character,
        game_state,
        route=route,
        mechanical_events=events,
        inventory_sync=True,
    )
    assert character.is_item_equipped("撬棍")
    assert not any("跳过装备" in event for event in sync_events)
