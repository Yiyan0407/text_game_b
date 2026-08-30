from unittest.mock import MagicMock

from game.auto_combat import run_auto_combat
from game.models import Character, CombatEnemy, CombatState, GameState
from game.orchestrator import GameOrchestrator
from tests.fixtures_effects import forged_weapon


def test_run_auto_combat_player_wins():
    cutter = forged_weapon("分子切割器", "2d10")
    character = Character(name="测试", strength=18, inventory=[cutter])
    character.equip_item("分子切割器", slot="body")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[
            CombatEnemy(
                name="变异体",
                hp=8,
                max_hp=8,
                ac=5,
                attack_bonus=-5,
                attack_damage="1d4",
            )
        ],
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=12,
        movement_remaining_m=12,
        enemy_distances={"变异体": 10},
    )
    result = run_auto_combat(character, game_state)
    assert result.outcome == "victory"
    assert not game_state.is_in_combat()
    assert any("自动战斗" in event for event in result.events)
    assert any("攻击 变异体" in event for event in result.events)


def test_run_auto_combat_not_in_combat():
    character = Character(name="测试")
    game_state = GameState()
    result = run_auto_combat(character, game_state)
    assert result.outcome == "not_in_combat"
    assert result.events == []


def test_orchestrator_auto_combat_turn_mechanical_only():
    cutter = forged_weapon("分子切割器", "2d10")
    character = Character(name="测试", strength=18, inventory=[cutter])
    character.equip_item("分子切割器", slot="body")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[
            CombatEnemy(
                name="变异体",
                hp=8,
                max_hp=8,
                ac=5,
                attack_bonus=-5,
                attack_damage="1d4",
            )
        ],
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=12,
        movement_remaining_m=12,
        enemy_distances={"变异体": 2},
    )
    orchestrator = GameOrchestrator(kp_chain=MagicMock())
    (
        rejection,
        pre_events,
        _run_state,
        _stream,
        _item_sync,
        _mem,
        _finish,
        _rollback,
    ) = orchestrator.auto_combat_turn_stream(
        character,
        game_state,
        MagicMock(format_for_prompt=lambda: ""),
        [],
    )
    assert rejection is None
    assert not game_state.is_in_combat()
    assert any("自动战斗" in event for event in pre_events)
