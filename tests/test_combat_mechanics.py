from unittest.mock import patch

from game.combat import end_combat, maybe_end_combat, player_attack, resolve_pickup_in_combat, resolve_talk, start_combat
from game.combat_constraints import format_combat_constraints_for_kp
from game.models import Character, CombatEnemy, CombatState, DiceRoll, GameState
from game.results import ActionRouteResult
from game.state_patch import apply_state_patch, patch_from_dict
from game.weapon_combat import resolve_weapon_profile
from chain.action_router import ActionRouter
from tests.fixtures_effects import forged_heal_item, forged_martial_skill, forged_weapon


def _approved_route(**kwargs) -> ActionRouteResult:
    return ActionRouteResult(approved=True, **kwargs)


def test_resolve_weapon_profile_firearm_vs_unarmed():
    armed = Character(
        name="测试",
        inventory=[forged_weapon("格洛克手枪")],
        skills=["射击（手枪）"],
    )
    profile = resolve_weapon_profile(armed)
    assert profile.use_dex is True
    assert profile.damage_notation == "1d10"
    assert profile.attack_bonus == 0

    unarmed = Character(name="测试")
    fist = resolve_weapon_profile(unarmed)
    assert fist.label == "徒手"
    assert fist.damage_notation == "1d4"
    assert fist.attack_bonus == 0


def test_resolve_weapon_profile_stacks_skill_with_equipped_weapon():
    martial = Character(
        name="测试",
        inventory=[forged_weapon("凡剑", "1d6")],
        skills=[forged_martial_skill("裂气斩", "2d10")],
    )
    martial.equip_item("凡剑", slot="hand")
    route = _approved_route(
        skill_usage="use",
        referenced_skills=["裂气斩"],
        action_intent="凡剑引气，裂气斩",
    )
    profile = resolve_weapon_profile(martial, route)
    assert profile.label == "凡剑（裂气斩）"
    assert profile.damage_notation == "1d6+2d10"
    assert profile.attack_bonus == 2
    assert profile.item_name == "凡剑"


def test_player_attack_stacks_weapon_and_skill_damage():
    character = Character(
        name="测试",
        strength=16,
        inventory=[forged_weapon("凡剑", "1d6")],
        skills=[forged_martial_skill("裂气斩", "2d10")],
    )
    character.equip_item("凡剑", slot="hand")
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="靶子", hp=200, max_hp=200, ac=5, attack_bonus=0, sp=0)],
        turn_order=["player", "靶子"],
        turn_index=0,
        enemy_distances={"靶子": 2},
    )
    route = _approved_route(
        combat_action="attack",
        attack_target="靶子",
        skill_usage="use",
        referenced_skills=["裂气斩"],
        action_intent="凡剑裂气斩",
    )
    with patch("game.combat.roll", return_value=DiceRoll(notation="1d20+3", rolls=[15], modifier=3, total=18)):
        with patch("game.combat.roll_damage", return_value=DiceRoll(notation="1d6+2d10", rolls=[3, 8, 9], modifier=0, total=20)):
            result = player_attack(character, state, "靶子", route=route)
    assert "凡剑（裂气斩）" in result
    assert state.combat.enemies[0].hp == 200 - (20 + 3)


def test_resolve_weapon_profile_martial_unarmed():
    martial = Character(name="测试", skills=[forged_martial_skill("奔雷掌")])
    fist = resolve_weapon_profile(martial)
    assert fist.label == "徒手"
    assert fist.damage_notation == "1d4"

    route = _approved_route(
        skill_usage="use",
        referenced_skills=["奔雷掌"],
        action_intent="一掌封喉",
    )
    profile = resolve_weapon_profile(martial, route)
    assert profile.label == "徒手（奔雷掌）"
    assert profile.damage_notation == "1d8"
    assert profile.attack_bonus == 2
    assert profile.use_dex is False
    assert "奔雷掌" in profile.label


def test_player_attack_uses_martial_profile_label():
    character = Character(
        name="测试",
        strength=16,
        skills=[forged_martial_skill("奔雷掌")],
    )
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


def test_validate_allows_deescalation_talk_as_bonus_after_attack():
    route = _approved_route(
        mode="combat",
        combat_action="talk",
        attack_target="安保支援人员",
        action_cost="main",
        action_intent="收刀威慑，要求放下武器",
        needs_roll=True,
        roll_type="ability_check",
        ability="cha",
        dc=14,
    )
    character = Character(name="测试", cha=14)
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[
            CombatEnemy(name="安保支援人员", hp=4, max_hp=12, ac=12),
            CombatEnemy(name="同伴", hp=12, max_hp=12, ac=12),
        ],
        turn_order=["player"],
        turn_index=0,
        action_used=True,
    )
    result = ActionRouter.validate(
        route,
        character,
        game_state,
        user_input="收刀，不再攻击。我对另一个举切割器：放下武器，否则下一个是你。",
    )
    assert result.approved is True
    assert result.action_cost == "bonus"


def test_validate_rejects_talk_when_both_actions_exhausted():
    route = _approved_route(
        mode="combat",
        combat_action="talk",
        attack_target="安保支援人员",
        action_cost="main",
        action_intent="收刀威慑",
    )
    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="安保支援人员", hp=4, max_hp=12, ac=12)],
        turn_order=["player"],
        turn_index=0,
        action_used=True,
        bonus_action_used=True,
    )
    result = ActionRouter.validate(
        route,
        character,
        game_state,
        user_input="收刀，不再攻击，放下武器。",
    )
    assert result.approved is False
    assert "结束回合" in result.rejection_reason


def test_combat_constraints_for_blocked_attack():
    route = _approved_route(action_intent="射击瘦高个", scope_stop="仍与光头对峙")
    text = format_combat_constraints_for_kp(
        ["本回合主要动作已用尽。可使用附加动作，或输入「结束回合」。"],
        route,
    )
    assert "不得写射击命中" in text or "不得" in text


def test_combat_constraints_for_out_of_range_attack():
    text = format_combat_constraints_for_kp(
        ["无法攻击 未知实体：超出射程（4m > 2m）（当前 4m）。"],
        None,
    )
    assert "超出射程" in text
    assert "不得" in text


def test_damage_constraints_for_successful_attack():
    text = format_combat_constraints_for_kp(
        [
            "攻击 路人（凡剑（裂气斩），2m）：命中！伤害 2d8+1d6 = 18。路人 剩余 HP 0/6 路人 被击倒！"
        ],
        None,
    )
    assert "伤害约束" in text
    assert "禁止编造" in text
    assert "凡剑（裂气斩）" in text


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
                    "description": "从敌人处夺取",
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
        inventory_sync=True,
    )
    assert any("跳过重复添加" in event for event in events)
    assert not character.has_inventory_item("格洛克手枪")


def test_state_patch_blocks_duplicate_after_mechanical_equip():
    character = Character(name="测试", inventory=[forged_weapon("格洛克手枪")])
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
            "装备：格洛克手枪（手持）",
            "具体效果由 KP 叙事描述。",
        ],
    )
    assert any("跳过重复添加" in event for event in events)
    item = character.find_inventory_item("格洛克手枪")
    assert item is not None
    assert item.quantity == 1


def test_state_patch_blocks_duplicate_after_mechanical_pickup():
    character = Character(name="测试", inventory=[forged_weapon("格洛克手枪")])
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
                {"action": "add", "item": "格洛克手枪", "quantity": 1, "unit": "把", "description": "战斗缴获"}
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
    events = orchestrator._resolve_mechanics(route, character, game_state, None)
    assert any("免费物件互动：拾取 格洛克手枪" in event for event in events)
    assert not character.has_inventory_item("格洛克手枪")
    assert game_state.combat.free_interact_used is True
    assert game_state.combat.has_bonus_action() is True


def test_pickup_weapon_then_attack_without_extra_draw():
    from game.combat import resolve_pickup_in_combat, player_attack
    from game.effects import EntityEffects
    from game.post_kp_mechanics import resolve_post_kp_mechanics

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
    route = _approved_route(item_usage="pickup", referenced_items=["格洛克手枪"])
    pickup_events = resolve_pickup_in_combat(character, game_state, ["格洛克手枪"])
    assert any("免费物件互动" in event for event in pickup_events)
    assert game_state.combat.free_interact_used is True
    settle_events = resolve_post_kp_mechanics(
        route, character, game_state, pickup_events
    )
    assert any("获得" in event for event in settle_events)
    item = character.find_inventory_item("格洛克手枪")
    assert item is not None
    item.effects = EntityEffects(attack_damage="1d10", use_dex=True, forged=True)
    character.equip_item("格洛克手枪", slot="hand")

    attack_route = _approved_route(
        combat_action="attack",
        attack_target="敌人",
        referenced_items=["格洛克手枪"],
        move_meters=8,
        move_target="敌人",
    )
    result = player_attack(character, game_state, "敌人", route=attack_route)
    assert "免费物件互动" not in result
    assert game_state.combat.has_bonus_action() is True


def test_attack_from_inventory_requires_free_interact():
    from game.inventory import InventoryItem

    character = Character(
        name="测试",
        inventory=[
            InventoryItem(
                name="格洛克手枪",
                quantity=1,
                unit="把",
                effects={"attack_damage": "1d10", "use_dex": True, "forged": True},
            )
        ],
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


def test_attack_with_equipped_body_weapon_skips_draw():
    from game.combat import player_attack
    from tests.fixtures_effects import forged_weapon

    cutter = forged_weapon("分子切割器", "2d10")
    character = Character(name="测试", inventory=[cutter])
    character.equip_item("分子切割器", slot="body")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=20, max_hp=20, ac=5)],
        turn_order=["player"],
        turn_index=0,
        enemy_distances={"敌人": 2},
        free_interact_used=True,
    )
    route = _approved_route(
        combat_action="attack",
        attack_target="敌人",
        referenced_items=["分子切割器"],
    )
    result = player_attack(character, game_state, "敌人", route=route)
    assert "分子切割器" in result
    assert "免费物件互动已用尽" not in result
    assert character.is_item_equipped("分子切割器")


def test_use_equipped_attack_weapon_does_not_unequip():
    from game.item_use import resolve_use_item
    from tests.fixtures_effects import forged_weapon

    cutter = forged_weapon("分子切割器", "2d10")
    character = Character(name="测试", inventory=[cutter])
    character.equip_item("分子切割器", slot="hand")
    events = resolve_use_item(character, ["分子切割器"])
    assert any("已装备并就绪" in event for event in events)
    assert character.is_item_equipped("分子切割器")
    assert not any("卸下" in event for event in events)


def test_validate_forces_combat_use_item_cost():
    route = _approved_route(
        mode="combat",
        item_usage="use",
        referenced_items=["治疗药水"],
        action_intent="喝治疗药水",
    )
    character = Character(name="测试", inventory=[forged_heal_item()])
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
    )
    character = Character(name="测试", inventory=[forged_heal_item()])
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="敌人", hp=10, max_hp=10, ac=12)],
        turn_order=["player"],
        turn_index=0,
    )
    route = _approved_route(item_usage="use", referenced_items=["治疗药水"])
    events = orchestrator._resolve_mechanics(route, character, game_state, None)
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


def test_orchestrator_attack_after_approach_at_melee_range():
    from game.orchestrator import GameOrchestrator
    from tests.fixtures_effects import forged_weapon

    cutter = forged_weapon("分子切割器", "2d10")
    character = Character(name="测试", strength=16, inventory=[cutter])
    character.equip_item("分子切割器", slot="hand")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=30, max_hp=30, ac=5)],
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=12,
        movement_remaining_m=12,
        enemy_distances={"变异体": 10},
    )
    route = _approved_route(
        mode="combat",
        combat_action="attack",
        attack_target="变异体",
        move_meters=8,
        move_target="变异体",
        action_cost="main",
    )
    from unittest.mock import MagicMock

    orchestrator = GameOrchestrator(kp_chain=MagicMock(), action_router=MagicMock())
    events = orchestrator._resolve_mechanics(route, character, game_state, None)
    joined = " ".join(events)
    assert "靠近 8m" in joined
    assert game_state.combat.enemy_distances["变异体"] == 2
    assert "无法攻击" not in joined
    assert "攻击 变异体" in joined
    assert not game_state.combat.has_main_action()


def test_player_attack_rejects_out_of_range():
    character = Character(
        name="测试",
        inventory=[forged_weapon("格洛克手枪")],
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


def test_combat_use_item_cost_free_when_hand_equipped():
    from game.combat_item_use import combat_use_item_cost
    from game.inventory import InventoryItem

    character = Character(
        name="测试",
        inventory=[
            InventoryItem(name="多功能装置", quantity=1, unit="套", kind="durable")
        ],
    )
    character.equip_item("多功能装置", slot="hand")
    assert combat_use_item_cost(character, "多功能装置") == "free"


def test_combat_use_item_cost_free_from_effects_gear_slot():
    from game.combat_item_use import combat_use_item_cost
    from game.inventory import InventoryItem

    character = Character(
        name="测试",
        inventory=[
            InventoryItem(
                name="多功能装置",
                quantity=1,
                unit="套",
                kind="durable",
                effects={"gear_slot": "tool", "forged": True},
            )
        ],
    )
    assert combat_use_item_cost(character, "多功能装置") == "free"


def test_successful_deescalation_talk_ends_combat_without_enemy_attack(monkeypatch):
    from game.models import DiceRoll
    from game.results import AbilityCheckResult

    def _success_check(*args, **kwargs):
        return AbilityCheckResult(
            ability="cha",
            dc=14,
            roll=DiceRoll(notation="1d20", rolls=[17], modifier=3, total=20),
            check_total=20,
            success=True,
        )

    monkeypatch.setattr("game.combat.ability_check", _success_check)

    character = Character(name="测试", cha=16)
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=2,
        enemies=[
            CombatEnemy(name="领头安保", hp=4, max_hp=12, ac=12, attack_bonus=3),
            CombatEnemy(name="同伴", hp=12, max_hp=12, ac=12, attack_bonus=3),
        ],
        turn_order=["player", "同伴", "领头安保"],
        turn_index=0,
        action_used=True,
    )
    result = resolve_talk(
        character,
        state,
        "同伴",
        dc=14,
        action_cost="bonus",
        action_intent="收刀，不再攻击，放下武器否则下一个是你",
    )
    assert "成功" in result
    assert "已投降" in result
    assert "战斗结束" in result
    assert not state.is_in_combat()


def test_incapacitated_enemy_cannot_act():
    enemy = CombatEnemy(name="领头", hp=4, max_hp=12, ac=12)
    assert enemy.can_act() is False


def test_maybe_end_combat_when_only_incapacitated_or_surrendered_remain():
    character = Character(name="测试")
    state = GameState()
    state.combat = CombatState(
        active=True,
        round=1,
        enemies=[
            CombatEnemy(name="领头", hp=4, max_hp=12, ac=12, surrendered=False),
            CombatEnemy(name="同伴", hp=12, max_hp=12, ac=12, surrendered=True),
        ],
        turn_order=["player"],
        turn_index=0,
    )
    msg, defeated = maybe_end_combat(state, character)
    assert msg is not None
    assert not state.is_in_combat()
