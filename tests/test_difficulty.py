from game.difficulty import DC_MAX, DC_MIN, clamp_dc, ensure_ability_check_dc, infer_ability_check_dc, is_valid_dc
from game.results import ActionRouteResult


def test_clamp_dc():
    assert clamp_dc(3) == DC_MIN
    assert clamp_dc(22) == 22
    assert clamp_dc(99) == DC_MAX


def test_preserves_ai_dc_in_validate():
    from chain.action_router import ActionRouter
    from game.models import Character, GameState

    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="int",
        dc=22,
        action_intent="黑入核心服务器",
    )
    result = ActionRouter.validate(route, Character(name="测试"), GameState())
    assert result.approved is True
    assert result.dc == 22


def test_infer_dc_for_high_security_infiltration():
    dc = infer_ability_check_dc(
        ability="dex",
        action_intent="沿消防通道继续深入",
        user_input="继续深入",
        context="安保在前台巡逻，机房重地非授权禁止入内，监控全覆盖",
    )
    assert dc >= 16


def test_infer_dc_for_easy_task():
    dc = infer_ability_check_dc(
        ability="wis",
        action_intent="轻松辨认常见渔网",
        user_input="看看这张网",
        context="",
    )
    assert dc <= 12


def test_validate_infers_when_dc_missing():
    from chain.action_router import ActionRouter
    from game.models import Character, GameState

    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="cha",
        dc=0,
        action_intent="说服守卫",
    )
    result = ActionRouter.validate(
        route,
        Character(name="测试"),
        GameState(),
        user_input="我尝试说服守卫",
    )
    assert result.approved is True
    assert is_valid_dc(result.dc)
    assert result.dc != 0
