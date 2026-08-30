from game.combat import player_attack, player_move
from game.combat_targets import normalize_enemy_ref, parse_hold_distance_meters, resolve_living_enemy_ref
from game.models import Character, CombatEnemy, CombatState, GameState
from game.orchestrator import GameOrchestrator
from game.results import ActionRouteResult
from chain.action_router import ActionRouter, _normalize_hold_distance_move
from tests.fixtures_effects import forged_weapon


def test_resolve_unknown_entity_to_single_enemy():
    combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12)],
        turn_order=["player"],
        turn_index=0,
        enemy_distances={"变异体": 0},
    )
    assert resolve_living_enemy_ref(combat, "未知实体") == "变异体"
    assert combat.distance_to("未知实体") == 0


def test_attack_after_move_uses_same_distance_key():
    cutter = forged_weapon("分子切割器", "2d10")
    character = Character(name="测试", strength=16, inventory=[cutter])
    character.equip_item("分子切割器", slot="body")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=300, max_hp=300, ac=25)],
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=12,
        movement_remaining_m=12,
        enemy_distances={"变异体": 8},
    )
    route = ActionRouteResult(
        approved=True,
        mode="combat",
        combat_action="attack",
        attack_target="未知实体",
        move_target="未知实体",
        move_meters=8,
        move_toward=True,
        action_cost="main",
    )
    from unittest.mock import MagicMock

    orchestrator = GameOrchestrator(kp_chain=MagicMock(), action_router=MagicMock())
    events = orchestrator._resolve_mechanics(route, character, game_state, None)
    joined = " ".join(events)
    assert game_state.combat.enemy_distances["变异体"] == 0
    assert "无法攻击" not in joined
    assert "攻击 变异体" in joined


def test_validate_resolves_unknown_entity_for_attack():
    character = Character(
        name="测试",
        inventory=[forged_weapon("分子切割器", "2d10")],
    )
    character.equip_item("分子切割器", slot="hand")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12)],
        turn_order=["player"],
        turn_index=0,
        enemy_distances={"变异体": 0},
    )
    route = ActionRouteResult(
        approved=True,
        mode="combat",
        combat_action="attack",
        attack_target="未知实体",
        action_cost="main",
    )
    result = ActionRouter.validate(route, character, game_state, user_input="向变异体发动攻击")
    assert result.approved is True
    assert result.attack_target == "变异体"


def test_hold_one_meter_moves_toward_when_far():
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12, start_distance_m=10)],
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=12,
        movement_remaining_m=12,
        enemy_distances={"变异体": 10},
    )
    route = ActionRouteResult(
        approved=True,
        mode="combat",
        combat_action="move",
        move_target="变异体",
        move_meters=1,
        move_toward=False,
        action_cost="free",
    )
    _normalize_hold_distance_move(
        route,
        game_state.combat,
        "和变异体保持一米距离",
    )
    assert route.move_toward is True
    assert route.move_meters == 9

    character = Character(name="测试")
    result = player_move(
        character,
        game_state,
        normalize_enemy_ref(game_state.combat, route.move_target),
        route.move_meters,
        toward=route.move_toward,
    )
    assert "靠近 9m" in result
    assert game_state.combat.enemy_distances["变异体"] == 1


def test_parse_hold_distance_meters():
    assert parse_hold_distance_meters("和变异体保持一米距离") == 1
    assert parse_hold_distance_meters("保持 2 米间隔") == 2
