from game.combat import _resolve_enemy_turn, advance_after_player_action, resolve_until_player_turn
from game.combat_range import enemy_attack_range_status, enemy_weapon_range_m
from game.models import Character, CombatEnemy, CombatState, GameState


def test_ranged_enemy_retreats_when_too_close():
    character = Character(name="测试", hp=20, max_hp=20)
    enemy = CombatEnemy(
        name="枪手",
        hp=12,
        max_hp=12,
        ac=12,
        attack_damage="1d10",
        use_dex=True,
        attack_bonus=20,
        start_distance_m=10,
    )
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[enemy],
        turn_order=["枪手"],
        turn_index=0,
        enemy_distances={"枪手": 0},
    )
    event = _resolve_enemy_turn(state.combat, character, state)
    assert event is not None
    assert "后撤" in event
    assert state.combat.enemy_distances["枪手"] == 2
    assert "攻击你" in event
    assert "够不着" not in event


def test_ranged_enemy_uses_gun_butt_when_pinned_at_melee():
    character = Character(name="测试", hp=20, max_hp=20, ac=10)
    enemy = CombatEnemy(
        name="枪手",
        hp=12,
        max_hp=12,
        ac=12,
        attack_damage="1d10",
        use_dex=True,
        attack_bonus=10,
        start_distance_m=0,
    )
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[enemy],
        turn_order=["枪手"],
        turn_index=0,
        enemy_distances={"枪手": 0},
    )
    # 模拟无法后撤：先把距离钉在 0，并跳过 reposition 效果——直接测 fallback
    from game.combat_range import apply_ranged_melee_fallback, enemy_attack_profile, enemy_weapon_range_m

    profile, applied = apply_ranged_melee_fallback(
        0,
        enemy_attack_profile(enemy),
        range_m=enemy_weapon_range_m(enemy),
    )
    assert applied
    assert profile.damage_notation == "1d4"
    assert "枪托" in profile.label


def test_melee_enemy_weapon_range():
    enemy = CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12, attack_damage="2d10")
    assert enemy_weapon_range_m(enemy) == (0, 2, 2)


def test_artillery_enemy_inferred_from_damage():
    enemy = CombatEnemy(
        name="T-90",
        hp=100,
        max_hp=100,
        ac=18,
        attack_damage="3d8",
        sp_max=45,
        start_distance_m=40,
    )
    assert enemy_weapon_range_m(enemy)[2] == 150


def test_ranged_enemy_explicit_range():
    enemy = CombatEnemy(
        name="狙击手",
        hp=12,
        max_hp=12,
        ac=13,
        attack_damage="1d10",
        use_dex=True,
        attack_range_normal_m=80,
        attack_range_max_m=120,
    )
    assert enemy_weapon_range_m(enemy) == (2, 80, 120)


def test_melee_enemy_cannot_attack_at_distance():
    character = Character(name="测试", hp=20, max_hp=20)
    enemy = CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12, attack_damage="2d10")
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[enemy],
        turn_order=["变异体"],
        turn_index=0,
        enemy_distances={"变异体": 10},
    )
    in_range, _, note = enemy_attack_range_status(10, enemy)
    assert not in_range
    assert "超出射程" in note

    event = _resolve_enemy_turn(state.combat, character, state)
    assert event is not None
    assert "靠近" in event
    assert "够不着你" in event
    assert state.combat.enemy_distances["变异体"] == 4
    assert character.hp == 20


def test_melee_enemy_attacks_in_range():
    character = Character(name="测试", hp=20, max_hp=20)
    enemy = CombatEnemy(
        name="变异体",
        hp=20,
        max_hp=20,
        ac=12,
        attack_damage="2d10",
        attack_bonus=20,
    )
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[enemy],
        turn_order=["变异体"],
        turn_index=0,
        enemy_distances={"变异体": 2},
    )
    event = _resolve_enemy_turn(state.combat, character, state)
    assert event is not None
    assert "攻击你" in event
    assert "够不着" not in event


def test_ranged_enemy_attacks_without_approaching():
    character = Character(name="测试", hp=20, max_hp=20)
    enemy = CombatEnemy(
        name="枪手",
        hp=12,
        max_hp=12,
        ac=12,
        attack_damage="1d10",
        use_dex=True,
        attack_bonus=20,
        start_distance_m=25,
    )
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[enemy],
        turn_order=["枪手"],
        turn_index=0,
        enemy_distances={"枪手": 25},
    )
    event = _resolve_enemy_turn(state.combat, character, state)
    assert event is not None
    assert "靠近" not in event
    assert "攻击你" in event
    assert "25m" in event


def test_enemy_turn_resolves_after_player_action():
    character = Character(name="测试", hp=20, max_hp=20)
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12, attack_damage="2d10")],
        turn_order=["player", "变异体"],
        turn_index=0,
        enemy_distances={"变异体": 10},
        action_used=True,
    )
    events = advance_after_player_action(character, state)
    assert any("够不着你" in event for event in events)
    assert character.hp == 20
