from game.combat import parse_enemies, player_attack, resolve_pickup_in_combat, start_combat, end_combat
from game.models import Character, CombatEnemy, CombatState, GameState


def test_parse_enemies():
    enemies = parse_enemies("守卫:12:12,野狗:8:10")
    assert len(enemies) == 2
    assert enemies[0].name == "守卫"
    assert enemies[0].ac == 12


def test_start_combat():
    character = Character(name="测试", dex=14)
    state = GameState()
    result = start_combat(character, state, "哥布林:8:11")
    assert state.combat is not None
    assert state.combat.active
    assert "战斗开始" in result


def test_player_attack():
    character = Character(name="测试", strength=16)
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="靶子", hp=20, max_hp=20, ac=5)],
        turn_order=["player", "靶子"],
        turn_index=0,
    )
    result = player_attack(character, state, "靶子")
    assert "攻击" in result
    enemy = state.combat.get_enemy("靶子")
    assert enemy.hp <= 20


def test_end_combat():
    state = GameState()
    character = Character(name="测试")
    start_combat(character, state, "敌人:5:10")
    msg = end_combat(state)
    assert "战斗结束" in msg
    assert state.combat is None


def test_resolve_pickup_in_combat_uses_bonus_action():
    character = Character(name="测试")
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player", "守卫"],
        turn_index=0,
    )
    events = resolve_pickup_in_combat(character, state, ["药瓶"])
    assert any("药瓶" in event for event in events)
    assert character.has_inventory_item("药瓶")
    assert state.combat.bonus_action_used is True
    assert state.combat.has_main_action() is True
