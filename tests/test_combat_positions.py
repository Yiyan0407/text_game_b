from game.combat import _pick_enemy_attack_target, player_move, start_combat
from game.combat_allies import _ally_reposition
from game.models import Character, CombatAlly, CombatEnemy, CombatState, GameState
from game.results import EnemyDefPatch


def test_player_move_does_not_drag_enemy_when_ally_repositions():
    character = Character(name="玩家", dex=12)
    combat = CombatState(
        active=True,
        round=1,
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=9,
        movement_remaining_m=9,
        unit_positions_m={
            "player": (0, 0),
            "拾荒者": (20, 0),
            "枪手": (-2, 2),
        },
        enemies=[
            CombatEnemy(name="拾荒者", hp=10, max_hp=10, ac=10, start_distance_m=20),
        ],
        allies=[
            CombatAlly(
                name="枪手",
                hp=14,
                max_hp=14,
                ac=12,
                attack_damage="1d8",
                start_distance_m=20,
            )
        ],
    )
    state = GameState(combat=combat)
    ally = combat.allies[0]
    enemy = combat.enemies[0]
    player_before = combat.get_position("player")
    _ally_reposition(combat, ally, enemy)
    assert combat.get_position("player") == player_before
    assert combat.get_position("枪手") != (-2, 2)


def test_enemy_picks_closer_ally():
    character = Character(name="玩家", hp=20)
    combat = CombatState(
        active=True,
        unit_positions_m={
            "player": (0, 0),
            "枪手": (5, 0),
            "拾荒者": (8, 0),
        },
        enemies=[
            CombatEnemy(name="拾荒者", hp=10, max_hp=10, ac=10, start_distance_m=8),
        ],
        allies=[
            CombatAlly(name="枪手", hp=10, max_hp=10, ac=12, start_distance_m=5),
        ],
    )
    target = _pick_enemy_attack_target(combat, character, combat.enemies[0])
    assert target == ("ally", "枪手")


def test_player_move_toward_enemy_on_grid():
    character = Character(name="玩家", dex=14)
    state = GameState(
        combat=CombatState(
            active=True,
            turn_order=["player"],
            turn_index=0,
            movement_speed_m=9,
            movement_remaining_m=9,
            unit_positions_m={"player": (0, 0), "敌人": (20, 0)},
            enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=10, start_distance_m=20)],
        )
    )
    msg = player_move(character, state, "敌人", 6, toward=True)
    assert "靠近" in msg
    assert state.combat.get_position("player") == (6, 0)
    assert state.combat.distance_between("player", "敌人") == 14


def test_start_combat_sets_unit_positions():
    character = Character(name="玩家", dex=12)
    state = GameState()
    start_combat(
        character,
        state,
        "测试:8:10",
        enemy_defs=[
            EnemyDefPatch(
                name="狙击手",
                hp=10,
                ac=12,
                start_distance_m=100,
                start_x_m=100,
                start_y_m=0,
            )
        ],
    )
    assert state.combat.get_position("狙击手") == (100, 0)
    assert state.combat.distance_between("player", "狙击手") == 100
