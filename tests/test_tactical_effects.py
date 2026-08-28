"""烟雾/闪光战术加值与 AOE 消耗品测试。"""

from game.combat import player_ac, resolve_combat_ability_check
from game.combat_modifiers import (
    FLASH_PLAYER_CHECK_BONUS,
    SMOKE_ENEMY_ATTACK_PENALTY,
    SMOKE_PLAYER_AC_BONUS,
    SMOKE_PLAYER_CHECK_BONUS,
    player_check_bonus,
)
from game.effect_use import resolve_item_use
from game.models import Character, CombatEnemy, CombatState, GameState
from tests.fixtures_effects import forged_aoe_grenade, forged_smoke


def test_smoke_sets_cover_and_ac_bonus():
    character = Character(name="测试", dexterity=14, inventory=[forged_smoke()])
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=12)],
        turn_order=["player"],
        turn_index=0,
    )
    item = character.find_inventory_item("烟雾弹")
    events = resolve_item_use(character, item, "烟雾弹", game_state=state)
    assert events
    assert state.combat.smoke_cover_rounds >= 1
    assert any("烟雾" in line for line in events)
    assert player_ac(character, state) == player_ac(character) + SMOKE_PLAYER_AC_BONUS
    assert player_check_bonus(state.combat, "dex") == SMOKE_PLAYER_CHECK_BONUS


def test_smoke_applies_to_combat_ability_check(monkeypatch):
    from game.models import DiceRoll

    monkeypatch.setattr(
        "game.dice.roll",
        lambda notation: DiceRoll(notation=notation, rolls=[15], total=15),
    )

    character = Character(name="测试", wisdom=10)
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=12)],
        turn_order=["player"],
        turn_index=0,
        smoke_cover_rounds=2,
    )
    text = resolve_combat_ability_check(
        character,
        "wis",
        15,
        "感知检定",
        game_state=state,
    )
    assert "成功" in text
    assert f"+{SMOKE_PLAYER_CHECK_BONUS}" in text or "环境" in text


def test_aoe_grenade_hits_all_living_enemies(monkeypatch):
    from game import dice

    monkeypatch.setattr(dice, "roll_damage", lambda _: type("R", (), {"total": 8, "describe": lambda: "2d6[4+4]"})())

    character = Character(name="测试", dexterity=14, inventory=[forged_aoe_grenade()])
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[
            CombatEnemy(name="甲", hp=20, max_hp=20, ac=10),
            CombatEnemy(name="乙", hp=20, max_hp=20, ac=10),
        ],
        turn_order=["player"],
        turn_index=0,
    )
    item = character.find_inventory_item("手雷")
    events = resolve_item_use(
        character,
        item,
        "手雷",
        game_state=state,
        attack_target="甲",
    )
    assert any("甲" in line for line in events)
    assert any("乙" in line for line in events)
    assert state.combat.get_enemy("甲").hp < 20
    assert state.combat.get_enemy("乙").hp < 20


def test_flash_reduces_enemy_attack_modifier():
    character = Character(name="测试", dexterity=10)
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=20, max_hp=20, ac=10, attack_bonus=5, damage="1d6")],
        turn_order=["player", "敌人"],
        turn_index=1,
        flash_disorient_rounds=1,
    )
    from game.combat_modifiers import enemy_attack_roll_modifier

    assert enemy_attack_roll_modifier(state.combat) == -2
    assert player_check_bonus(state.combat, "int") == FLASH_PLAYER_CHECK_BONUS
