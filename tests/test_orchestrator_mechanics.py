from game.adventure_snapshot import restore_adventure, snapshot_adventure
from game.models import Character, CombatEnemy, CombatState, GameState
from game.orchestrator import GameOrchestrator
from game.results import ActionRouteResult
from tests.fixtures_effects import forged_heal_item


def test_restore_adventure_reverts_mutations():
    character = Character(name="艾拉", hp=20, max_hp=20)
    game_state = GameState(turn_count=3, current_scene="码头")
    char_snap, state_snap = snapshot_adventure(character, game_state)

    character.hp = 5
    game_state.turn_count = 9
    game_state.current_scene = "酒馆"

    restore_adventure(character, game_state, char_snap, state_snap)

    assert character.hp == 20
    assert game_state.turn_count == 3
    assert game_state.current_scene == "码头"


def test_resolve_mechanics_rejects_combat_action_when_not_player_turn():
    orchestrator = GameOrchestrator()
    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12, attack_bonus=-5)],
        turn_order=["守卫", "player"],
        turn_index=0,
    )
    route = ActionRouteResult(
        approved=True,
        mode="combat",
        combat_action="attack",
        attack_target="守卫",
        action_intent="攻击守卫",
    )

    try:
        orchestrator._resolve_mechanics(route, character, game_state, None)
        raised = False
    except ValueError as exc:
        raised = True
        assert "还没轮到你" in str(exc)

    assert raised


def test_resolve_mechanics_rejects_trigger_combat_attack_before_player_turn():
    from unittest.mock import patch

    orchestrator = GameOrchestrator()
    character = Character(name="测试")
    game_state = GameState()
    route = ActionRouteResult(
        approved=True,
        mode="combat",
        trigger_combat=True,
        enemies_spec="守卫:12:12",
        combat_action="attack",
        attack_target="守卫",
        action_intent="拔剑砍向守卫",
    )

    def _start_combat(_character, state, _spec, **kwargs):
        state.combat = CombatState(
            active=True,
            round=1,
            enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12, attack_bonus=-5)],
            turn_order=["守卫", "player"],
            turn_index=0,
        )
        return "战斗开始"

    with patch("game.orchestrator.start_combat", side_effect=_start_combat):
        with patch("game.orchestrator.resolve_until_player_turn", return_value=[]):
            try:
                orchestrator._resolve_mechanics(route, character, game_state, None)
                raised = False
            except ValueError as exc:
                raised = True
                assert "无法在同一句话里立刻执行" in str(exc)

    assert raised


def test_resolve_post_kp_use_item_in_exploration():
    from game.post_kp_mechanics import resolve_post_kp_mechanics

    character = Character(name="测试", hp=5, max_hp=20, inventory=[forged_heal_item()])
    game_state = GameState()
    route = ActionRouteResult(
        approved=True,
        item_usage="use",
        referenced_items=["治疗药水"],
    )

    events = resolve_post_kp_mechanics(route, character, game_state)

    assert any("使用" in event for event in events)
    assert character.hp > 5
    assert not character.has_inventory_item("治疗药水")
