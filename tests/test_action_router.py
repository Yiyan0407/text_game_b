import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chain.action_router import ActionRouter
from game.models import Character, ChatMessage, GameState
from game.orchestrator import GameOrchestrator
from game.narrative_brief import build_narrative_brief_static
from game.results import ActionRouteResult, StatePatch, TurnResult
from game.scenario import Scenario


def _setup_async_mocks(router, kp, state_agent=None):
    router.aevaluate = AsyncMock(side_effect=lambda *args, **kwargs: router.evaluate(*args, **kwargs))
    if state_agent is None:
        state_agent = MagicMock()
    state_agent.apropose = AsyncMock(return_value=StatePatch())
    turn_result = TurnResult(response="好的。", tool_events=[])
    if getattr(kp, "narrate", None) and kp.narrate.return_value:
        turn_result = kp.narrate.return_value
    kp.anarrate = AsyncMock(return_value=turn_result)
    return state_agent


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
        "action_intent": "调查周围",
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
        "action_intent": "悄悄靠近",
    }
    route = ActionRouter._parse_route(json.dumps(payload))
    assert route.approved is True
    assert route.needs_roll is True
    assert route.ability == "dex"
    assert route.dc == 14


def test_parse_route_from_markdown_json():
    payload = {
        "approved": True,
        "action_intent": "答应老周，一起查看压缩包",
        "needs_roll": False,
        "roll_type": "none",
    }
    wrapped = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    route = ActionRouter._parse_route(wrapped)
    assert route.approved is True
    assert "压缩包" in route.action_intent


def test_parse_route_tolerates_invalid_dc_and_string_list_fields():
    payload = {
        "approved": True,
        "action_intent": "检查文件",
        "dc": "偏高",
        "must_not_narrate": "离开现场",
        "referenced_items": "手机",
    }
    route = ActionRouter._parse_route(json.dumps(payload, ensure_ascii=False))
    assert route.approved is True
    assert route.dc == 0
    assert route.must_not_narrate == ["离开现场"]
    assert route.referenced_items == ["手机"]


def test_parse_route_repairs_malformed_json():
    broken = "{'approved': True, 'action_intent': '答应老周一起查看压缩包',}"
    route = ActionRouter._parse_route(broken)
    assert route.approved is True
    assert "压缩包" in route.action_intent


def test_fallback_route_approves_short_dialogue_in_exploration():
    route = ActionRouter._fallback_route("行，我们一块看看吧", GameState())
    assert route.approved is True
    assert route.action_intent == "行，我们一块看看吧"


def test_fallback_route_stays_strict_in_combat():
    from game.models import CombatEnemy, CombatState

    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player"],
        turn_index=0,
    )
    route = ActionRouter._fallback_route("行，我们一块看看吧", game_state)
    assert route.approved is False


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


def test_infiltration_roll_skipped_for_dialogue_in_restricted_context():
    route = _approved_route(action_intent="悄悄询问公司内部情况")
    history = [
        ChatMessage(
            role="assistant",
            content="你来到星辰科技大楼，安保在前台巡逻，非授权人员禁止入内。",
        ),
    ]
    result = ActionRouter._maybe_require_infiltration_roll(
        route,
        "我悄悄问前台能否介绍一下公司内部架构",
        history,
    )
    assert result.needs_roll is False


def test_require_infiltration_roll_for_continue_deeper():
    route = _approved_route(action_intent="沿消防通道继续深入")
    history = [
        ChatMessage(
            role="assistant",
            content="你来到星辰科技大楼，安保在前台巡逻，机房重地非授权禁止入内。",
        ),
    ]
    result = ActionRouter._maybe_require_infiltration_roll(
        route,
        "继续深入",
        history,
    )
    assert result.needs_roll is True
    assert result.roll_type == "ability_check"
    assert result.ability == "dex"
    assert result.dc >= 14


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
    state_agent = _setup_async_mocks(router, kp)
    orchestrator = GameOrchestrator(
        kp_chain=kp, action_router=router, state_agent=state_agent
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
    assert len(turn.tool_events) == 1
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
    state_agent = _setup_async_mocks(router, kp)
    orchestrator = GameOrchestrator(kp_chain=kp, action_router=router, state_agent=state_agent)
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
    state_agent = _setup_async_mocks(router, kp)
    orchestrator = GameOrchestrator(kp_chain=kp, action_router=router, state_agent=state_agent)
    character = Character(name="测试", strength=16)
    game_state = GameState()
    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=[CombatEnemy(name="哥布林", hp=10, max_hp=10, ac=5, attack_bonus=-5)],
        turn_order=["player", "哥布林"],
        turn_index=0,
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


def test_apply_granularity_allows_compound_action():
    route = _approved_route(
        action_intent="购买连弩和短剑并询问盔甲",
        scope_stop="交易与询价完成",
    )
    ActionRouter._finalize_scope(route)
    assert route.approved is True
    assert route.scope_stop


def test_apply_granularity_allows_single_purchase_action():
    route = _approved_route(
        action_intent="向瘦小摊主购买破禁符",
        scope_stop="破禁符到手、交易完成",
        must_not_narrate=["离开坊市", "与沈渊会面"],
    )
    ActionRouter._finalize_scope(route)
    assert route.approved is True
    assert route.scope_stop
    assert route.must_not_narrate


def test_narrative_brief_includes_scope_and_mechanical_events():
    route = _approved_route(
        action_intent="向瘦小摊主购买破禁符",
        scope_stop="破禁符到手、仍停留在摊位前",
        must_not_narrate=["返回后院", "与沈渊对话"],
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
    assert "破禁符到手" in brief
    assert "【禁止推进】" in brief
    assert "返回后院" in brief
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
        enemies=[CombatEnemy(name="守卫", hp=12, max_hp=12, ac=12)],
        turn_order=["player", "守卫"],
        turn_index=0,
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
    assert result.action_cost == "bonus"


def test_validate_rejects_pickup_when_bonus_action_exhausted():
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
        bonus_action_used=True,
    )
    result = ActionRouter.validate(route, Character(name="测试"), game_state)
    assert result.approved is False
    assert "附加动作" in result.rejection_reason


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


def test_fallback_route_allows_compound_action():
    route = ActionRouter._fallback_route("购买食盐然后离开", GameState())
    ActionRouter._finalize_scope(route)
    assert route.approved is True


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
