from game.check_reroll import (
    apply_pending_reroll_to_route,
    apply_reroll_patch,
    record_ability_check,
)
from game.models import Character, GameState, LastAbilityCheckRecord, PendingReroll
from game.results import ActionRouteResult, RerollPatch


def test_apply_reroll_overturns_failure_and_grants_reroll():
    character = Character(name="测试", hp=15, max_hp=20)
    game_state = GameState(
        last_ability_check=LastAbilityCheckRecord(
            ability="dex",
            dc=18,
            check_total=12,
            roll_total=10,
            success=False,
            action_intent="走消防通道潜入",
            hp_before=20,
            hp_after=15,
        )
    )
    events = apply_reroll_patch(
        RerollPatch(
            overturn_failure=True,
            grant=True,
            adjusted_dc=12,
            action_hint="走消防通道潜入",
            reason="特工背景，原 DC 过高",
        ),
        character,
        game_state,
    )
    assert character.hp == 20
    assert game_state.last_ability_check is None
    assert game_state.pending_reroll is not None
    assert game_state.pending_reroll.adjusted_dc == 12
    assert any("撤销检定失败" in event for event in events)
    assert any("授予重掷" in event for event in events)


def test_pending_reroll_overrides_route_dc():
    game_state = GameState(
        pending_reroll=PendingReroll(
            adjusted_dc=12,
            reason="KP 修正 DC",
            action_hint="走消防通道潜入",
        ),
        last_ability_check=LastAbilityCheckRecord(
            ability="dex",
            dc=18,
            check_total=12,
            roll_total=10,
            success=False,
            action_intent="走消防通道潜入",
            user_input="走消防通道潜入",
        ),
    )
    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="dex",
        dc=18,
    )
    events = apply_pending_reroll_to_route(
        route, game_state, user_input="走消防通道潜入"
    )
    assert route.dc == 12
    assert game_state.pending_reroll is None
    assert any("重掷" in event for event in events)


def test_pending_reroll_not_applied_to_unrelated_action():
    game_state = GameState(
        pending_reroll=PendingReroll(
            adjusted_dc=12,
            reason="投掷武器射程远大于2m",
            action_hint="将锤子朝着怪物丢过去",
        ),
        last_ability_check=LastAbilityCheckRecord(
            ability="cha",
            dc=16,
            check_total=9,
            roll_total=6,
            success=False,
            action_intent="投掷锤子",
            user_input="将锤子朝着怪物丢过去",
        ),
    )
    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="dex",
        dc=14,
    )
    events = apply_pending_reroll_to_route(
        route,
        game_state,
        user_input="进通风管道，用分子切割器切开格栅",
    )
    assert route.dc == 14
    assert game_state.pending_reroll is None
    assert events == []


def test_record_ability_check_stores_context():
    character = Character(name="测试", hp=20, max_hp=20)
    game_state = GameState()
    character.hp = 18
    record_ability_check(
        game_state,
        character=character,
        ability="dex",
        dc=14,
        check_total=10,
        roll_total=8,
        success=False,
        action_intent="撬锁",
        user_input="撬锁",
        proficiency_bonus=True,
        hp_before=20,
    )
    assert game_state.last_ability_check is not None
    assert game_state.last_ability_check.dc == 14
    assert game_state.last_ability_check.hp_after == 18
    assert game_state.last_ability_check.success is False
