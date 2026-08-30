from game.combat import resolve_use_item_in_combat
from game.models import Character, CombatEnemy, CombatState, GameState
from game.post_kp_mechanics import resolve_post_kp_mechanics
from game.results import ActionRouteResult
from tests.fixtures_effects import forged_weapon


def test_throw_hammer_resolves_before_kp_narrative():
    character = Character(
        name="测试",
        inventory=[forged_weapon("锤子", "2d10")],
    )
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=20, max_hp=20, ac=5, sp=8, sp_max=8)],
        turn_order=["player"],
        turn_index=0,
        enemy_distances={"变异体": 5},
    )
    events = resolve_use_item_in_combat(
        character,
        state,
        ["锤子"],
        attack_target="变异体",
    )
    assert any("附加动作：使用" in event for event in events)
    assert any("投掷" in event for event in events)
    assert any("💥" in event for event in events)
    assert not character.has_inventory_item("锤子")

    route = ActionRouteResult(
        approved=True,
        item_usage="use",
        referenced_items=["锤子"],
        attack_target="变异体",
    )
    post_events = resolve_post_kp_mechanics(route, character, state, events)
    assert post_events == []
