from game.difficulty import DC_MAX, DC_MIN, clamp_dc, ensure_ability_check_dc, is_valid_dc
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


def test_validate_rejects_when_dc_missing():
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
    assert result.approved is False
    assert "DC" in result.rejection_reason


def test_ensure_ability_check_dc_rejects_invalid():
    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="dex",
        dc=0,
    )
    assert ensure_ability_check_dc(route) is False
    assert route.dc == 0


def test_ensure_ability_check_dc_clamps_valid():
    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="dex",
        dc=99,
    )
    assert ensure_ability_check_dc(route) is True
    assert route.dc == DC_MAX
    assert is_valid_dc(route.dc)
