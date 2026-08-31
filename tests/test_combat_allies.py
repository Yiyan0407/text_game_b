from unittest.mock import patch

from game.combat import (
    _pick_enemy_attack_target,
    _resolve_enemy_turn,
    advance_after_player_action,
    end_combat,
    start_combat,
)
from game.combat_allies import allies_from_route_defs, resolve_ally_turn
from game.models import (
    Character,
    CombatAlly,
    CombatEnemy,
    CombatState,
    GameState,
    NPCRelation,
    NpcCombatRecord,
)
from game.results import AllyDefPatch, EnemyDefPatch


def test_start_combat_includes_allies_in_turn_order():
    character = Character(name="玩家", dex=14)
    state = GameState()
    msg = start_combat(
        character,
        state,
        "拾荒者:8:11",
        enemy_defs=[EnemyDefPatch(name="拾荒者", hp=8, ac=11, start_distance_m=20)],
        ally_defs=[
            AllyDefPatch(
                name="枪手",
                hp=14,
                ac=12,
                attack_damage="2d8",
                attack_bonus=4,
                use_dex=True,
                start_distance_m=20,
            )
        ],
    )
    assert "枪手" in state.combat.turn_order
    assert "友方" in msg
    assert len(state.combat.allies) == 1


def test_ally_turn_damages_enemy():
    combat = CombatState(
        active=True,
        round=1,
        turn_order=["枪手", "player"],
        turn_index=0,
        enemies=[
            CombatEnemy(
                name="拾荒者",
                hp=12,
                max_hp=12,
                ac=10,
                start_distance_m=15,
            )
        ],
        allies=[
            CombatAlly(
                name="枪手",
                hp=14,
                max_hp=14,
                ac=12,
                attack_damage="1d8",
                attack_bonus=5,
                start_distance_m=2,
            )
        ],
        enemy_distances={"拾荒者": 2},
    )
    state = GameState(combat=combat)
    with patch("game.combat_allies.roll") as mock_roll:
        mock_roll.return_value.total = 18
        mock_roll.return_value.rolls = [18]
        with patch("game.combat_allies.roll_damage") as mock_damage:
            from game.models import DiceRoll

            mock_damage.return_value = DiceRoll(
                notation="2d8", rolls=[4, 5], modifier=0, total=9
            )
            event = resolve_ally_turn(combat, state)
    assert event is not None
    assert "【友方】枪手" in event
    assert combat.enemies[0].hp < 12


def test_advance_after_player_runs_ally_turn():
    character = Character(name="玩家", dex=12)
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        turn_order=["player", "枪手", "拾荒者"],
        turn_index=0,
        enemies=[
            CombatEnemy(
                name="拾荒者",
                hp=20,
                max_hp=20,
                ac=10,
                attack_bonus=-5,
                start_distance_m=20,
            )
        ],
        allies=[
            CombatAlly(
                name="枪手",
                hp=14,
                max_hp=14,
                ac=12,
                attack_damage="1d8",
                attack_bonus=3,
                start_distance_m=20,
            )
        ],
        enemy_distances={"拾荒者": 20},
    )
    with patch("game.combat_allies.resolve_ally_turn", return_value="【友方】枪手 攻击 拾荒者") as ally_turn:
        with patch("game.combat._resolve_enemy_turn", return_value="拾荒者 攻击你"):
            events = advance_after_player_action(character, state)
    assert any("枪手" in event for event in events)
    ally_turn.assert_called()
    assert state.combat.is_player_turn()


def test_ally_hp_persists_across_combats():
    state = GameState(
        npcs=[
            NPCRelation(
                name="枪手",
                attitude="friendly",
                combat=NpcCombatRecord(
                    hp=1,
                    max_hp=14,
                    ac=12,
                    attack_damage="2d8",
                    attack_bonus=4,
                    use_dex=True,
                ),
            )
        ]
    )
    allies, skipped = allies_from_route_defs(
        [
            AllyDefPatch(
                name="枪手",
                hp=14,
                ac=12,
                attack_damage="2d8",
                attack_bonus=4,
                use_dex=True,
            )
        ],
        game_state=state,
    )
    assert skipped == []
    assert len(allies) == 1
    assert allies[0].hp == 1


def test_dead_ally_skipped_on_rejoin():
    state = GameState(
        npcs=[
            NPCRelation(
                name="枪手",
                attitude="friendly",
                combat=NpcCombatRecord(hp=0, max_hp=14, ac=12, dead=True),
            )
        ]
    )
    allies, skipped = allies_from_route_defs(
        [AllyDefPatch(name="枪手", hp=14, ac=12)],
        game_state=state,
    )
    assert allies == []
    assert skipped == ["枪手"]


def test_end_combat_syncs_ally_state_and_death():
    character = Character(name="玩家")
    state = GameState(
        npcs=[NPCRelation(name="枪手", attitude="friendly")],
        combat=CombatState(
            active=True,
            allies=[
                CombatAlly(name="枪手", hp=0, max_hp=14, ac=12, attack_damage="1d8")
            ],
        ),
    )
    msg = end_combat(state)
    assert state.combat is None
    assert "阵亡" in msg
    npc = state.find_npc("枪手")
    assert npc.combat.dead is True
    assert npc.combat.hp == 0


def test_enemy_attacks_ally():
    character = Character(name="玩家", dex=12)
    combat = CombatState(
        active=True,
        round=1,
        turn_order=["拾荒者"],
        turn_index=0,
        enemies=[
            CombatEnemy(
                name="拾荒者",
                hp=10,
                max_hp=10,
                ac=10,
                attack_damage="1d6",
                attack_bonus=10,
                start_distance_m=2,
            )
        ],
        allies=[
            CombatAlly(
                name="枪手",
                hp=8,
                max_hp=8,
                ac=10,
                start_distance_m=2,
            )
        ],
        enemy_distances={"拾荒者": 2},
    )
    state = GameState(combat=combat)
    with patch("game.combat._pick_enemy_attack_target", return_value=("ally", "枪手")):
        with patch("game.combat.roll") as mock_roll:
            mock_roll.return_value.total = 20
            mock_roll.return_value.rolls = [20]
            with patch("game.combat.roll_damage") as mock_damage:
                from game.models import DiceRoll

                mock_damage.return_value = DiceRoll(
                    notation="1d6", rolls=[4], modifier=0, total=4
                )
                event = _resolve_enemy_turn(combat, character, state)
    assert event is not None
    assert "攻击 枪手" in event
    assert combat.allies[0].hp == 4


def test_pick_enemy_target_prefers_player_on_tie():
    character = Character(name="玩家", hp=20)
    combat = CombatState(
        active=True,
        allies=[CombatAlly(name="枪手", hp=10, max_hp=10, ac=12, start_distance_m=10)],
        enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=10, start_distance_m=10)],
        enemy_distances={"敌人": 10},
    )
    target = _pick_enemy_attack_target(
        combat, character, combat.enemies[0]
    )
    assert target == ("player", "player")
