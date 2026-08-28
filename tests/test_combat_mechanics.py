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
        enemy_distances={"靶子": 2},
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


def test_state_patch_blocks_duplicate_after_mechanical_equip():
    character = Character(name="测试", inventory=["格洛克手枪（1把）"])
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="光头", hp=12, max_hp=12, ac=12)],
        turn_order=["player"],
        turn_index=0,
    )
    route = _approved_route(
        item_usage="use",
        combat_action="use_item",
        referenced_items=["格洛克手枪"],
        action_intent="装备手枪",
    )
    patch = patch_from_dict(
        {
            "inventory": [
                {
                    "action": "add",
                    "item": "格洛克手枪",
                    "quantity": 1,
                    "unit": "把",
                    "description": "从敌人手中脱落",
                }
            ]
        }
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=[
            "持用：格洛克手枪（握持中）",
            "具体效果由 KP 叙事描述。",
        ],
    )
    assert any("跳过重复添加" in event for event in events)
    item = character.find_inventory_item("格洛克手枪")
    assert item is not None
    assert item.quantity == 1


def test_state_patch_blocks_duplicate_after_mechanical_pickup():
    character = Character(name="测试", inventory=["格洛克手枪（1把）"])
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player"],
        turn_index=0,
    )
    route = _approved_route(
        item_usage="pickup",
        referenced_items=["格洛克手枪"],
    )
    patch = patch_from_dict(
        {
            "inventory": [
                {"action": "add", "item": "格洛克手枪", "quantity": 1, "unit": "把"}
            ]
        }
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=["获得：格洛克手枪（1把）", "握持：格洛克手枪"],
    )
    assert any("机械层已结算" in event for event in events)
    item = character.find_inventory_item("格洛克手枪")
    assert item is not None
    assert item.quantity == 1


def test_state_patch_blocks_inventory_add_on_end_turn():
    character = Character(name="测试", inventory=["格洛克手枪（2把）"])
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[
            CombatEnemy(name="光头壮汉", hp=20, max_hp=20, ac=12),
            CombatEnemy(name="瘦高个", hp=15, max_hp=15, ac=12),
        ],
        turn_order=["player", "光头壮汉", "瘦高个"],
        turn_index=0,
    )
    route = _approved_route(
        combat_action="end_turn",
        action_cost="free",
        action_intent="结束回合",
    )
    patch = patch_from_dict(
        {
            "inventory": [
                {
                    "action": "add",
                    "item": "格洛克手枪",
                    "quantity": 4,
                    "unit": "把",
                    "description": "从光头壮汉手中脱落后拾取",
                }
            ]
        }
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=[
            "光头壮汉 靠近 6m（距离 4m）。 光头壮汉 攻击你：命中！",
            "瘦高个 靠近 6m（距离 4m）。 瘦高个 攻击你：未命中",
        ],
    )
    assert any("结束回合不会获得物品" in event for event in events)
    item = character.find_inventory_item("格洛克手枪")
    assert item.quantity == 2


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
    assert game_state.combat.free_interact_used is True
    assert game_state.combat.has_bonus_action() is True


def test_pickup_weapon_equips_without_extra_draw():
    from game.combat import resolve_pickup_in_combat, player_attack

    character = Character(name="测试", inventory=[], skills=["射击"])
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=20, max_hp=20, ac=5, start_distance_m=10)],
        turn_order=["player"],
        turn_index=0,
        enemy_distances={"敌人": 10},
    )
    pickup_events = resolve_pickup_in_combat(character, game_state, ["格洛克手枪"])
    assert any("握持" in event for event in pickup_events)
    assert game_state.combat.free_interact_used is True

    route = _approved_route(
        combat_action="attack",
        attack_target="敌人",
        referenced_items=["格洛克手枪"],
        move_meters=8,
        move_target="敌人",
    )
    result = player_attack(character, game_state, "敌人", route=route)
    assert "免费物件互动" not in result
    assert game_state.combat.has_bonus_action() is True


def test_attack_from_inventory_requires_free_interact():
    character = Character(
        name="测试",
        inventory=["格洛克手枪（1把）"],
        skills=["射击"],
    )
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=20, max_hp=20, ac=5)],
        turn_order=["player"],
        turn_index=0,
        enemy_distances={"敌人": 10},
        free_interact_used=True,
    )
    route = _approved_route(
        combat_action="attack",
        attack_target="敌人",
        referenced_items=["格洛克手枪"],
        move_meters=8,
        move_target="敌人",
    )
    result = player_attack(character, game_state, "敌人", route=route)
    assert "免费物件互动已用尽" in result
    assert game_state.combat.has_main_action() is True


def test_validate_forces_combat_use_item_cost():
    route = _approved_route(
        mode="combat",
        item_usage="use",
        referenced_items=["治疗药水"],
        action_intent="喝治疗药水",
    )
    character = Character(name="测试", inventory=["治疗药水"])
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=12)],
        turn_order=["player"],
        turn_index=0,
    )
    result = ActionRouter.validate(route, character, game_state)
    assert result.approved is True
    assert result.combat_action == "use_item"
    assert result.action_cost == "bonus"


def test_orchestrator_combat_use_item_spends_bonus():
    from unittest.mock import MagicMock

    from game.orchestrator import GameOrchestrator

    orchestrator = GameOrchestrator(
        kp_chain=MagicMock(),
        action_router=MagicMock(),
        state_agent=MagicMock(),
    )
    character = Character(name="测试", inventory=["治疗药水"])
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=12)],
        turn_order=["player"],
        turn_index=0,
    )
    route = _approved_route(item_usage="use", referenced_items=["治疗药水"])
    events = orchestrator._resolve_mechanics(route, character, game_state)
    assert any("使用" in event for event in events)
    assert game_state.combat.bonus_action_used is True


def test_player_move_does_not_use_main_action():
    from game.combat import player_move

    character = Character(name="测试", dexterity=14)
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=12)],
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=9,
        movement_remaining_m=9,
        enemy_distances={"敌人": 15},
    )
    result = player_move(character, game_state, "敌人", 5)
    assert "靠近 5m" in result
    assert game_state.combat.enemy_distances["敌人"] == 10
    assert game_state.combat.movement_remaining_m == 4
    assert game_state.combat.has_main_action() is True


def test_player_attack_rejects_out_of_range():
    character = Character(
        name="测试",
        inventory=["格洛克手枪（1把）"],
        skills=["射击"],
    )
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="远敌", hp=10, max_hp=10, ac=10)],
        turn_order=["player"],
        turn_index=0,
        enemy_distances={"远敌": 60},
    )
    route = _approved_route(
        combat_action="attack",
        attack_target="远敌",
        referenced_items=["格洛克手枪"],
    )
    result = player_attack(character, game_state, "远敌", route=route)
    assert "无法攻击" in result
    assert game_state.combat.has_main_action() is True


def test_validate_move_action_free_cost():
    route = _approved_route(
        mode="combat",
        combat_action="move",
        move_target="敌人",
        move_meters=3,
        action_intent="靠近敌人 3 米",
    )
    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=12)],
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=9,
        movement_remaining_m=9,
        enemy_distances={"敌人": 12},
    )
    result = ActionRouter.validate(route, character, game_state)
    assert result.approved is True
    assert result.action_cost == "free"


def test_parse_enemies_with_distance():
    from game.combat import parse_enemies

    enemies = parse_enemies("守卫:12:12:20")
    assert enemies[0].start_distance_m == 20


def test_resolve_dash_adds_movement():
    from game.combat import resolve_dash

    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=12)],
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=9,
        movement_remaining_m=3,
    )
    result = resolve_dash(character, game_state)
    assert "疾跑" in result
    assert game_state.combat.movement_remaining_m == 12
    assert game_state.combat.has_main_action() is False
