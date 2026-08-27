import json
from unittest.mock import MagicMock, patch

from chain.action_router import ActionRouter
from game.models import Character, ChatMessage, GameState
from game.orchestrator import GameOrchestrator, _strip_leaked_route_preamble
from game.results import ActionRouteResult, TurnResult
from game.scenario import Scenario, ScenarioNode


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


def test_validate_rejects_missing_skill():
    route = _approved_route(referenced_skills=["潜行"])
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
    orchestrator.kp.invoke.assert_not_called()


def test_validate_defaults_roll_when_needs_roll_without_roll_type():
    route = _approved_route(needs_roll=True, roll_type="none")
    character = Character(name="测试", cha=14)
    result = ActionRouter.validate(route, character, GameState())
    assert result.approved is True
    assert result.needs_roll is True
    assert result.roll_type == "ability_check"
    assert result.ability == "cha"
    assert result.dc == 14


def test_rescue_vague_destination_when_context_points_to_corp():
    route = ActionRouteResult(
        approved=False,
        rejection_reason="「去现场看看」目标不明确。请明确具体地点（如：星辰科技公司大堂）",
    )
    history = [
        ChatMessage(
            role="assistant",
            content="老周提到可通过星辰科技邮件服务器日志比对，确认这些邮件是否从内部发出。",
        ),
    ]
    scenario = Scenario(
        id="midnight_archive",
        title="午夜档案",
        world_id="modern",
        key_nodes=[
            ScenarioNode(id="corp_lobby", title="目标公司大堂", description="前台与安保"),
        ],
    )
    result = ActionRouter._maybe_rescue_vague_destination(
        route,
        "我直接去现场看看吧",
        history,
        scenario,
    )
    assert result.approved is True
    assert "目标公司大堂" in result.action_intent


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


def test_strip_leaked_route_preamble():
    raw = (
        "[行动裁定 — 探索]\n\n"
        "行动意图：沿消防通道继续深入\n"
        "叙事边界：抵达楼梯口\n\n"
        "你穿过走廊，朝消防通道的门走去。"
    )
    cleaned = _strip_leaked_route_preamble(raw)
    assert cleaned.startswith("你穿过走廊")
    assert "[行动裁定" not in cleaned


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
    kp.invoke.return_value = TurnResult(response="你成功听到了对话。", tool_events=[])
    orchestrator = GameOrchestrator(kp_chain=kp, action_router=router)
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
    kp.invoke.assert_called_once()
    assert kp.invoke.call_args.kwargs["skip_roll_tools"] is True
    kp_input = kp.invoke.call_args.kwargs["user_input"]
    assert "[行动裁定 — 探索]" in kp_input
    assert "机械结算结果" in kp_input


@patch("game.orchestrator.get_settings")
def test_orchestrator_always_routes_player_input(mock_settings):
    mock_settings.return_value = MagicMock(
        enable_action_suggestions=False,
        max_history_messages=40,
    )
    router = MagicMock()
    router.evaluate.return_value = _approved_route(action_intent="观察四周")
    kp = MagicMock()
    kp.invoke.return_value = TurnResult(response="好的。", tool_events=[])
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
    assert kp.invoke.call_args.kwargs["skip_roll_tools"] is True
    assert "[行动裁定" in kp.invoke.call_args.kwargs["user_input"]


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
    kp.invoke.return_value = TurnResult(response="你挥剑砍去。", tool_events=[])
    orchestrator = GameOrchestrator(kp_chain=kp, action_router=router)
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
    assert kp.invoke.call_args.kwargs["skip_combat_tools"] is True
    kp_input = kp.invoke.call_args.kwargs["user_input"]
    assert "仍可继续本回合行动" in kp_input


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


def test_apply_granularity_rejects_compound_action():
    route = _approved_route(
        action_intent="购买破禁符",
        scope_stop="交易完成",
    )
    result = ActionRouter._apply_granularity(
        route,
        "购买破禁符然后回去找沈渊",
    )
    assert result.approved is False
    assert "一次只描述一个行动" in result.rejection_reason


def test_apply_granularity_allows_single_purchase_action():
    route = _approved_route(
        action_intent="向瘦小摊主购买破禁符",
        scope_stop="破禁符到手、交易完成",
        must_not_narrate=["离开坊市", "与沈渊会面"],
    )
    result = ActionRouter._apply_granularity(
        route,
        "前往瘦小摊主处购买破禁符",
    )
    assert result.approved is True
    assert result.scope_stop
    assert result.must_not_narrate


def test_build_kp_input_includes_narrative_scope():
    route = _approved_route(
        action_intent="向瘦小摊主购买破禁符",
        scope_stop="破禁符到手、仍停留在摊位前",
        must_not_narrate=["返回后院", "与沈渊对话"],
    )
    kp_input = GameOrchestrator._build_kp_input(
        "前往瘦小摊主处购买破禁符",
        route,
        [],
        GameState(),
    )
    assert "叙事边界" in kp_input
    assert "本轮禁止叙事" in kp_input
    assert "不要链式推进" in kp_input
    assert "【NPC 同步】" in kp_input
    assert "record_npc" in kp_input
    assert "返回后院" in kp_input
