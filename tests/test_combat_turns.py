from game.combat import (
    advance_after_player_action,
    enemy_attack,
    maybe_end_combat,
    player_ac,
    resolve_until_player_turn,
    start_combat,
)
from game.models import Character, CombatEnemy, CombatState, GameState
from tests.fixtures_effects import forged_heal_item


def test_player_ac():
    character = Character(name="测试", dex=14)
    assert player_ac(character) == 12
    assert player_ac(character, defending=True) == 14


def test_enemy_attack_can_reduce_hp():
    character = Character(name="测试", hp=20, max_hp=20)
    enemy = CombatEnemy(name="哥布林", hp=10, max_hp=10, attack_bonus=20, damage_notation="1d6")
    result = enemy_attack(enemy, character)
    assert "攻击你" in result
    assert character.hp < 20


def test_advance_after_player_action_returns_to_player_turn():
    character = Character(name="测试", hp=20, max_hp=20)
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="哥布林", hp=10, max_hp=10, ac=10, attack_bonus=-5)],
        turn_order=["player", "哥布林"],
        turn_index=0,
    )
    events = advance_after_player_action(character, state)
    assert state.combat is not None
    assert state.combat.is_player_turn()
    assert isinstance(events, list)


def test_resolve_until_player_turn_when_enemy_first():
    character = Character(name="测试", hp=20, max_hp=20)
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="哥布林", hp=10, max_hp=10, ac=10, attack_bonus=-5)],
        turn_order=["哥布林", "player"],
        turn_index=0,
    )
    events = resolve_until_player_turn(character, state)
    assert state.combat.is_player_turn()
    assert len(events) >= 1


def test_maybe_end_combat_when_enemies_defeated():
    character = Character(name="测试")
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="哥布林", hp=0, max_hp=10, ac=10)],
        turn_order=["player"],
        turn_index=0,
    )
    msg, defeated = maybe_end_combat(state, character)
    assert msg is not None
    assert "战斗结束" in msg
    assert not state.is_in_combat()
    assert defeated is False


def test_combat_state_advance_turn_increments_round():
    combat = CombatState(
        active=True,
        round=1,
        turn_order=["player", "敌人"],
        turn_index=0,
    )
    combat.advance_turn()
    combat.advance_turn()
    assert combat.round == 2
    assert combat.turn_index == 0


def test_start_combat_sets_turn_index():
    character = Character(name="测试", dex=14)
    state = GameState()
    start_combat(character, state, "守卫:12:12")
    assert state.combat is not None
    assert state.combat.turn_index == 0
    assert len(state.combat.turn_order) == 2


def test_combat_state_resets_actions_on_player_turn():
    combat = CombatState(
        active=True,
        round=1,
        turn_order=["player", "敌人"],
        turn_index=0,
        action_used=True,
        bonus_action_used=True,
    )
    combat.advance_turn()
    combat.advance_turn()
    assert combat.is_player_turn()
    assert combat.has_main_action()
    assert combat.has_bonus_action()


def test_spend_action_or_error_blocks_double_main():
    from game.combat import spend_action_or_error

    combat = CombatState(
        active=True,
        round=1,
        turn_order=["player"],
        turn_index=0,
    )
    assert spend_action_or_error(combat, "main") is None
    assert combat.action_used
    err = spend_action_or_error(combat, "main")
    assert err is not None
    assert "主要动作" in err


def test_attack_then_use_item_does_not_end_turn():
    from game.combat import player_attack, resolve_use_item_in_combat

    character = Character(name="测试", strength=16, inventory=[forged_heal_item()])
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="哥布林", hp=10, max_hp=10, ac=5, start_distance_m=2)],
        turn_order=["player", "哥布林"],
        turn_index=0,
        enemy_distances={"哥布林": 2},
    )
    player_attack(character, state, "哥布林")
    assert state.combat.is_player_turn()
    assert not state.combat.has_main_action()
    assert state.combat.has_bonus_action()
    events = resolve_use_item_in_combat(
        character, state, ["治疗药水"], cost="bonus"
    )
    assert events
    assert "使用" in events[0]
    assert state.combat.is_player_turn()
    assert not state.combat.has_bonus_action()
