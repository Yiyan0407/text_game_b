from game.combat import player_attack, resolve_pickup_in_combat, start_combat
from game.combat_constraints import format_combat_constraints_for_kp
from game.models import Character, CombatEnemy, CombatState, GameState
from game.results import ActionRouteResult
from game.state_patch import apply_state_patch, patch_from_dict
from game.weapon_combat import resolve_weapon_profile
from chain.action_router import ActionRouter


def _approved_route(**kwargs) -> ActionRouteResult:
    return ActionRouteResult(approved=True, **kwargs)


def test_resolve_weapon_profile_firearm_vs_unarmed():
    armed = Character(
        name="测试",
        inventory=["格洛克手枪（1把）"],
        skills=["射击（手枪）"],
    )
    profile = resolve_weapon_profile(armed)
    assert profile.use_dex is True
    assert profile.damage_notation == "1d10"
    assert profile.attack_bonus == 2

    unarmed = Character(name="测试")
    fist = resolve_weapon_profile(unarmed)
    assert fist.label == "徒手"
    assert fist.damage_notation == "1d4"
    assert fist.attack_bonus == 0


def test_resolve_weapon_profile_martial_unarmed():
    martial = Character(name="测试", skills=["奔雷掌（贴身短打）"])
    profile = resolve_weapon_profile(martial)
    assert profile.label == "徒手（奔雷掌）"
    assert profile.damage_notation == "1d8"
    assert profile.attack_bonus == 2
    assert profile.use_dex is False

    route = _approved_route(
        skill_usage="use",
        referenced_skills=["奔雷掌"],
        action_intent="一掌封喉",
    )
    profile = resolve_weapon_profile(martial, route)
    assert "奔雷掌" in profile.label


def test_player_attack_uses_martial_profile_label():
    character = Character(name="测试", strength=16, skills=["奔雷掌"])
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="靶子", hp=20, max_hp=20, ac=5, attack_bonus=0)],
        turn_order=["player", "靶子"],
        turn_index=0,
    )
    route = _approved_route(
        combat_action="attack",
        attack_target="靶子",
        skill_usage="use",
        referenced_skills=["奔雷掌"],
        action_intent="奔雷掌击中靶子",
    )
    result = player_attack(character, state, "靶子", route=route)
    assert "奔雷掌" in result


def test_validate_rejects_pickup_and_attack_when_main_exhausted():
    route = _approved_route(
        mode="combat",
        combat_action="attack",
        attack_target="瘦高个",
        item_usage="pickup",
        referenced_items=["格洛克手枪"],
        action_cost="main",
        action_intent="捡起手枪并射击瘦高个",
    )
    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="瘦高个", hp=12, max_hp=12, ac=12)],
        turn_order=["player"],
        turn_index=0,
        action_used=True,
    )
    result = ActionRouter.validate(route, character, game_state)
    assert result.approved is False
    assert "主要动作已用尽" in result.rejection_reason


def test_combat_constraints_for_blocked_attack():
    route = _approved_route(action_intent="射击瘦高个", scope_stop="仍与光头对峙")
    text = format_combat_constraints_for_kp(
        ["本回合主要动作已用尽。可使用附加动作，或输入「结束回合」。"],
        route,
    )
    assert "不得写射击命中" in text or "不得" in text


def test_state_patch_blocks_combat_pickup_without_mechanical_gain():
    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="瘦高个", hp=12, max_hp=12, ac=12)],
        turn_order=["player"],
        turn_index=0,
        action_used=True,
    )
    route = _approved_route(item_usage="pickup", referenced_items=["格洛克手枪"])
    patch = patch_from_dict(
        {
            "inventory": [
                {
                    "action": "add",
                    "item": "格洛克手枪",
                    "quantity": 1,
                    "unit": "把",
                }
            ]
        }
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=["本回合主要动作已用尽。可使用附加动作，或输入「结束回合」。"],
    )
    assert any("跳过重复添加" in event for event in events)
    assert not character.has_inventory_item("格洛克手枪")


def test_orchestrator_pickup_branch_in_combat():
    from unittest.mock import MagicMock

    from game.orchestrator import GameOrchestrator

    orchestrator = GameOrchestrator(
        kp_chain=MagicMock(),
        action_router=MagicMock(),
        state_agent=MagicMock(),
    )
    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="瘦高个", hp=12, max_hp=12, ac=12)],
        turn_order=["player"],
        turn_index=0,
    )
    route = _approved_route(item_usage="pickup", referenced_items=["格洛克手枪"])
    events = orchestrator._resolve_mechanics(route, character, game_state)
    assert any("获得：格洛克手枪" in event for event in events)
    assert game_state.combat.bonus_action_used is True
