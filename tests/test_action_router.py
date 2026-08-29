import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chain.action_router import ActionRouter
from game.models import Character, ChatMessage, GameState
from game.orchestrator import GameOrchestrator
from game.narrative_brief import build_narrative_brief_static
from game.results import ActionRouteResult, StatePatch, TurnResult
from game.scenario import Scenario


def _setup_async_mocks(router, kp):
    router.aevaluate = AsyncMock(side_effect=lambda *args, **kwargs: router.evaluate(*args, **kwargs))
    turn_result = TurnResult(response="好的。", tool_events=[])
    if getattr(kp, "narrate", None) and kp.narrate.return_value:
        turn_result = kp.narrate.return_value
    kp.anarrate = AsyncMock(return_value=turn_result)


def _approved_route(**overrides) -> ActionRouteResult:
    data = {
        "approved": True,
        "rejection_reason": "",
        "needs_roll": False,
        "roll_type": "none",
        "ability": "",
        "dc": 0,
        "dice_notation": "",
        "referenced_items": [],
        "referenced_skills": [],
        "item_usage": "none",
    }
    data.update(overrides)
    return ActionRouteResult(**data)


def test_validate_skill_use_forces_proficiency_bonus():
    route = _approved_route(
        referenced_skills=["潜行"],
        skill_usage="use",
        needs_roll=True,
        roll_type="ability_check",
        ability="dex",
        dc=14,
    )
    character = Character(name="测试", skills=["潜行"])
    result = ActionRouter.validate(route, character, GameState())
    assert result.proficiency_bonus is True


def test_validate_clears_proficiency_bonus_when_no_roll():
    route = _approved_route(proficiency_bonus=True)
    character = Character(name="测试")
    result = ActionRouter.validate(route, character, GameState())
    assert result.proficiency_bonus is False


def test_validate_allows_learn_skill_without_having_it():
    route = _approved_route(
        referenced_skills=["潜行"],
        skill_usage="learn",
        needs_roll=True,
        roll_type="ability_check",
        ability="dex",
        dc=14,
    )
    character = Character(name="测试", skills=[])
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is True


def test_validate_rejects_learn_when_already_has_skill():
    route = _approved_route(referenced_skills=["潜行"], skill_usage="learn")
    character = Character(name="测试", skills=["潜行"])
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is False
    assert "已经掌握" in result.rejection_reason


def test_validate_rejects_missing_skill():
    route = _approved_route(referenced_skills=["潜行"], skill_usage="use")
    character = Character(name="测试", skills=["观察"])
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is False
    assert "潜行" in result.rejection_reason


def test_validate_rejects_missing_inventory_item_on_use():
    route = _approved_route(
        referenced_items=["火把"],
        item_usage="use",
        action_intent="使用火把照明",
    )
    character = Character(name="测试", inventory=["手机"])
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is False
    assert "火把" in result.rejection_reason


def test_validate_allows_fuzzy_skill_match():
    route = _approved_route(referenced_skills=["基础潜行"])
    character = Character(name="测试", skills=["基础潜行术"])
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is True


def test_validate_allows_pickup_without_inventory():
    route = _approved_route(
        referenced_items=["钥匙"],
        item_usage="pickup",
        action_intent="捡起地上的钥匙",
    )
    character = Character(name="测试")
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is True


def test_parse_route_rejects_invalid_json():
    route = ActionRouter._parse_route("not json")
    assert route.approved is False
    assert route.rejection_reason


def test_parse_route_from_json():
    payload = {
        "approved": True,
        "rejection_reason": "",
        "needs_roll": True,
        "roll_type": "ability_check",
        "ability": "dex",
        "dc": 14,
        "dice_notation": "",
        "referenced_items": [],
        "referenced_skills": [],
        "item_usage": "none",
    }
    route = ActionRouter._parse_route(json.dumps(payload))
    assert route.approved is True
    assert route.needs_roll is True
    assert route.ability == "dex"
    assert route.dc == 14


def test_parse_route_from_markdown_json():
    payload = {
        "approved": True,
        "needs_roll": False,
        "roll_type": "none",
        "item_usage": "observe",
    }
    wrapped = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    route = ActionRouter._parse_route(wrapped)
    assert route.approved is True
    assert route.item_usage == "observe"


def test_parse_route_tolerates_invalid_dc_and_string_list_fields():
    payload = {
        "approved": True,
        "dc": "偏高",
        "referenced_items": "手机",
    }
    route = ActionRouter._parse_route(json.dumps(payload, ensure_ascii=False))
    assert route.approved is True
    assert route.dc == 0
    assert route.referenced_items == ["手机"]


def test_parse_route_repairs_malformed_json():
    broken = "{'approved': True, 'item_usage': 'observe',}"
    route = ActionRouter._parse_route(broken)
    assert route.approved is True
    assert route.item_usage == "observe"



@patch("game.orchestrator.get_settings")
def test_orchestrator_reject_does_not_increment_turn(mock_settings):
    mock_settings.return_value = MagicMock(
        enable_action_suggestions=False,
        max_history_messages=40,
    )
    router = MagicMock()
    router.evaluate.return_value = ActionRouteResult(
        approved=False,
        rejection_reason="现代都市中无法召唤齐天大圣。",
    )
    router.aevaluate = AsyncMock(return_value=router.evaluate.return_value)
    orchestrator = GameOrchestrator(kp_chain=MagicMock(), action_router=router)
    character = Character(name="测试")
    game_state = GameState(turn_count=3)
    scenario = Scenario(id="test", title="测试", world_id="modern")

    turn = orchestrator.player_turn(
        character=character,
        game_state=game_state,
        scenario=scenario,
        user_input="我让齐天大圣上我身",
        history=[],
    )

    assert turn.rejected is True
    assert game_state.turn_count == 3
    orchestrator.kp.anarrate.assert_not_called()


def test_validate_rejects_roll_when_needs_roll_without_roll_type():
    route = _approved_route(needs_roll=True, roll_type="none")
    character = Character(name="测试", cha=14)
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is False
    assert result.needs_roll is False
    assert "缺少掷骰类型" in result.rejection_reason


@patch("game.orchestrator.get_settings")
def test_orchestrator_pre_roll_before_kp(mock_settings):
    mock_settings.return_value = MagicMock(
        enable_action_suggestions=False,
        max_history_messages=40,
    )
    router = MagicMock()
    router.evaluate.return_value = _approved_route(
        needs_roll=True,
        roll_type="ability_check",
        ability="dex",
        dc=14,
        action_intent="悄悄偷听对话",
    )
    kp = MagicMock()
    kp.narrate.return_value = TurnResult(response="你成功听到了对话。", tool_events=[])
    _setup_async_mocks(router, kp)
    orchestrator = GameOrchestrator(
        kp_chain=kp, action_router=router
    )
    character = Character(name="测试", dex=14)
    game_state = GameState()
    scenario = Scenario(id="test", title="测试", world_id="modern")

    turn = orchestrator.player_turn(
        character=character,
        game_state=game_state,
        scenario=scenario,
        user_input="我悄悄偷听对话",
        history=[],
    )

    assert turn.rejected is False
    assert any("检定" in event for event in turn.tool_events)
    assert "敏捷检定" in turn.tool_events[0]
    kp.anarrate.assert_called_once()
    kp_input = kp.anarrate.call_args.kwargs["user_input"]
    assert "【叙事简报】" in kp_input
    assert "悄悄偷听对话" in kp_input


@patch("game.orchestrator.get_settings")
def test_orchestrator_always_routes_player_input(mock_settings):
    mock_settings.return_value = MagicMock(
        enable_action_suggestions=False,
        max_history_messages=40,
    )
    router = MagicMock()
    router.evaluate.return_value = _approved_route(action_intent="观察四周")
    kp = MagicMock()
    kp.narrate.return_value = TurnResult(response="好的。", tool_events=[])
    _setup_async_mocks(router, kp)
    orchestrator = GameOrchestrator(kp_chain=kp, action_router=router)
    character = Character(name="测试")
    game_state = GameState()
    scenario = Scenario(id="test", title="测试", world_id="modern")

    orchestrator.player_turn(
        character=character,
        game_state=game_state,
        scenario=scenario,
        user_input="观察四周",
        history=[],
    )

    router.evaluate.assert_called_once()
    assert "【叙事简报】" in kp.anarrate.call_args.kwargs["user_input"]


@patch("game.orchestrator.get_settings")
def test_orchestrator_combat_attack_does_not_advance_until_actions_spent(mock_settings):
    from game.models import CombatEnemy, CombatState

    mock_settings.return_value = MagicMock(
        enable_action_suggestions=False,
        max_history_messages=40,
    )
    router = MagicMock()
    router.evaluate.return_value = _approved_route(
        mode="combat",
        combat_action="attack",
        attack_target="哥布林",
        action_cost="main",
        action_intent="攻击哥布林",
    )
    kp = MagicMock()
    kp.narrate.return_value = TurnResult(response="你挥剑砍去。", tool_events=[])
    _setup_async_mocks(router, kp)
    orchestrator = GameOrchestrator(kp_chain=kp, action_router=router)
    character = Character(name="测试", strength=16)
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="哥布林", hp=50, max_hp=50, ac=15, attack_bonus=-5, start_distance_m=2)],
        turn_order=["player", "哥布林"],
        turn_index=0,
        enemy_distances={"哥布林": 2},
    )
    turn = orchestrator.player_turn(
        character=character,
        game_state=game_state,
        scenario=Scenario(id="test", title="测试", world_id="modern"),
        user_input="攻击哥布林",
        history=[],
    )
    assert turn.rejected is False
    assert game_state.combat.is_player_turn()
    assert not game_state.combat.has_main_action()
    assert game_state.combat.has_bonus_action()
    kp.anarrate.assert_called_once()
    kp_input = kp.anarrate.call_args.kwargs["user_input"]
    assert "攻击哥布林" in kp_input
    assert "【模式】战斗" in kp_input


def test_validate_rejects_non_player_turn_in_combat():
    from game.models import CombatEnemy, CombatState

    route = _approved_route(
        mode="combat",
        combat_action="attack",
        attack_target="守卫",
        action_intent="攻击守卫",
    )
    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["守卫", "player"],
        turn_index=0,
    )
    result = ActionRouter.validate(route, character, game_state)
    assert result.approved is False
    assert "还没轮到你" in result.rejection_reason


def test_validate_rejects_exhausted_main_action():
    from game.models import CombatEnemy, CombatState

    route = _approved_route(
        mode="combat",
        combat_action="attack",
        attack_target="守卫",
        action_cost="main",
        action_intent="攻击守卫",
    )
    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player", "守卫"],
        turn_index=0,
        action_used=True,
    )
    result = ActionRouter.validate(route, character, game_state)
    assert result.approved is False
    assert "主要动作" in result.rejection_reason


def test_validate_allows_combat_interact_with_roll():
    from game.models import CombatEnemy, CombatState

    route = _approved_route(
        mode="combat",
        combat_action="interact",
        action_cost="main",
        needs_roll=True,
        roll_type="ability_check",
        ability="str",
        dc=14,
        action_intent="推翻桌子作掩体",
    )
    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player"],
        turn_index=0,
    )
    result = ActionRouter.validate(route, character, game_state)
    assert result.approved is True
    assert result.needs_roll is True


def test_validate_trigger_combat_requires_enemies_spec():
    route = _approved_route(
        trigger_combat=True,
        enemies_spec="",
        mode="combat",
        combat_action="attack",
        attack_target="守卫",
    )
    result = ActionRouter.validate(route, Character(name="测试"), GameState())
    assert result.approved is False
    assert "攻击目标" in result.rejection_reason or "无法确定" in result.rejection_reason


def test_validate_trigger_combat_clears_same_turn_combat_action():
    route = _approved_route(
        trigger_combat=True,
        enemies_spec="守卫:12:12",
        mode="combat",
        combat_action="attack",
        attack_target="守卫",
        item_usage="use",
        referenced_items=["短剑"],
    )
    result = ActionRouter.validate(route, Character(name="测试"), GameState())
    assert result.approved is True
    assert result.combat_action == "none"
    assert result.item_usage == "none"


def test_apply_granularity_allows_compound_action():
    route = _approved_route(
        item_usage="purchase",
        payment_items=["金币"],
        referenced_items=["连弩", "短剑"],
    )
    assert route.approved is True


def test_apply_granularity_allows_single_purchase_action():
    route = _approved_route(
        item_usage="purchase",
        payment_items=["定金币"],
        referenced_items=["破禁符"],
    )
    assert route.approved is True


def test_narrative_brief_includes_mechanical_events():
    route = _approved_route(
        item_usage="purchase",
        payment_items=["定金币"],
        referenced_items=["破禁符"],
    )
    brief = build_narrative_brief_static(
        "前往瘦小摊主处购买破禁符",
        route,
        ["背包新增：破禁符。当前：定金币（14枚）、破禁符"],
    )
    assert "【叙事简报】" in brief
    assert "【玩家输入】" in brief
    assert "背包新增：破禁符" in brief
    assert "前往瘦小摊主处购买破禁符" in brief


def test_validate_rejects_empty_attack_target():
    from game.models import CombatEnemy, CombatState

    route = _approved_route(
        mode="combat",
        combat_action="attack",
        attack_target="",
        action_intent="攻击敌人",
    )
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player", "守卫"],
        turn_index=0,
    )
    result = ActionRouter.validate(route, Character(name="测试"), game_state)
    assert result.approved is False
    assert "攻击" in result.rejection_reason


def test_validate_resolves_fuzzy_attack_target():
    from game.models import CombatEnemy, CombatState

    route = _approved_route(
        mode="combat",
        combat_action="attack",
        attack_target="前面的守卫",
        action_intent="攻击守卫",
    )
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12, start_distance_m=2)],
        turn_order=["player", "守卫"],
        turn_index=0,
        enemy_distances={"守卫": 2},
    )
    result = ActionRouter.validate(route, Character(name="测试"), game_state)
    assert result.approved is True
    assert result.attack_target == "守卫"


def test_validate_allows_pickup_in_combat():
    from game.models import CombatEnemy, CombatState

    route = _approved_route(
        mode="combat",
        item_usage="pickup",
        referenced_items=["药瓶"],
        action_intent="拾取药瓶",
    )
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player", "守卫"],
        turn_index=0,
    )
    result = ActionRouter.validate(route, Character(name="测试"), game_state)
    assert result.approved is True
    assert result.action_cost == "free"


def test_validate_rejects_pickup_when_free_interact_exhausted():
    from game.models import CombatEnemy, CombatState

    route = _approved_route(
        mode="combat",
        item_usage="pickup",
        referenced_items=["药瓶"],
        action_intent="拾取药瓶",
    )
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player", "守卫"],
        turn_index=0,
        free_interact_used=True,
    )
    result = ActionRouter.validate(route, Character(name="测试"), game_state)
    assert result.approved is False
    assert "免费物件互动" in result.rejection_reason


def test_validate_rejects_purchase_in_combat():
    from game.models import CombatEnemy, CombatState

    route = _approved_route(
        mode="combat",
        item_usage="purchase",
        payment_items=["定金币"],
        referenced_items=["药瓶"],
        action_intent="购买药瓶",
    )
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player", "守卫"],
        turn_index=0,
    )
    result = ActionRouter.validate(route, Character(name="测试"), game_state)
    assert result.approved is False
    assert "购买" in result.rejection_reason



def test_narrative_brief_includes_failed_purchase_event():
    route = _approved_route(
        item_usage="purchase",
        payment_items=["定金币"],
        referenced_items=["破禁符"],
        action_intent="购买破禁符",
    )
    brief = build_narrative_brief_static(
        "买破禁符",
        route,
        ["支付失败：背包中 定金币（0枚） 数量不足。"],
    )
    assert "支付失败" in brief
    assert "买破禁符" in brief


def test_action_router_prompt_formats_without_missing_variables():
    router = ActionRouter()
    formatted = router.prompt.format_messages(
        world_rules="规则",
        scenario_context="模组",
        game_state_context="状态",
        character_name="测试",
        character_background="背景",
        character_abilities="属性",
        hp=10,
        max_hp=10,
        character_inventory="空",
        character_equipment="无",
        character_skills="无",
        recent_history="",
        user_input="攻击保安",
    )
    assert formatted
    assert '"name"' in formatted[0].content


def test_validate_remaps_use_item_to_attack_when_input_attacks():
    from game.models import CombatEnemy, CombatState
    from tests.fixtures_effects import forged_weapon

    cutter = forged_weapon("分子切割器", "2d10")
    character = Character(name="测试", inventory=[cutter])
    character.equip_item("分子切割器", slot="hand")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12)],
        turn_order=["player"],
        turn_index=0,
        enemy_distances={"变异体": 2},
    )
    route = _approved_route(
        mode="combat",
        item_usage="use",
        combat_action="use_item",
        referenced_items=["分子切割器"],
        attack_target="变异体",
    )
    result = ActionRouter.validate(
        route,
        character,
        game_state,
        user_input="使用分子切割器进行攻击",
    )
    assert result.approved is True
    assert result.combat_action == "attack"
    assert result.item_usage == "none"


def test_validate_auto_fills_approach_move_for_attack():
    from game.models import CombatEnemy, CombatState
    from tests.fixtures_effects import forged_weapon

    cutter = forged_weapon("分子切割器", "2d10")
    character = Character(name="测试", inventory=[cutter])
    character.equip_item("分子切割器", slot="hand")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12)],
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
        move_meters=4,
        move_target="变异体",
    )
    result = ActionRouter.validate(
        route,
        character,
        game_state,
        user_input="接近他到攻击距离。使用分子切割器进行攻击",
    )
    assert result.approved is True
    assert result.move_meters == 8
    assert result.combat_action == "attack"


def test_validate_upgrades_move_to_attack_when_input_includes_attack():
    from game.models import CombatEnemy, CombatState

    character = Character(name="测试")
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12)],
        turn_order=["player"],
        turn_index=0,
        movement_speed_m=12,
        movement_remaining_m=12,
        enemy_distances={"变异体": 10},
    )
    route = _approved_route(
        mode="combat",
        combat_action="move",
        move_target="变异体",
        move_meters=4,
        action_cost="free",
    )
    result = ActionRouter.validate(
        route,
        character,
        game_state,
        user_input="接近他到攻击距离。使用分子切割器进行攻击",
    )
    assert result.combat_action == "attack"
    assert result.attack_target == "变异体"

