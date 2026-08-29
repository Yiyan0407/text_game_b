from game.check_consequences import (
    apply_check_failure_consequences,
    format_check_failure_constraints_for_kp,
    is_dangerous_attempt,
    is_social_attempt,
    is_stealth_attempt,
)
from game.effects import EntityEffects
from game.models import Character, GameState, NPCRelation
from game.narrative_brief import build_narrative_brief_static
from game.results import AbilityCheckResult, ActionRouteResult
from game.models import DiceRoll


def _route(**kwargs) -> ActionRouteResult:
    return ActionRouteResult(approved=True, **kwargs)

def _failed_result(*, ability: str = "dex", dc: int = 18, total: int = 7) -> AbilityCheckResult:
    return AbilityCheckResult(
        ability=ability,
        dc=dc,
        roll=DiceRoll(notation="1d20", rolls=[total], modifier=0, total=total),
        check_total=total,
        success=False,
    )


def test_is_stealth_attempt():
    route = _route()
    assert is_stealth_attempt("悄悄潜入仓库后门", route)


def test_check_failure_records_memory_and_damage():
    text = "攀爬破损外墙进入二楼"
    route = _route(ability="dex")
    character = Character(name="测试", hp=20, max_hp=20, dex=8)
    state = GameState()
    result = _failed_result(ability="dex", dc=18, total=7)
    events = apply_check_failure_consequences(
        route, result, character, state, user_input=text
    )
    assert any("行动失败" in event for event in events)
    assert any("受到" in event or "伤害" in event for event in events)
    assert character.hp < 20
    assert any("攀爬" in fact for fact in state.memory_facts)


def test_check_failure_social_worsens_npc_attitude():
    text = "向老周师傅求情"
    route = _route(ability="cha")
    character = Character(name="测试", cha=8)
    state = GameState(
        npcs=[NPCRelation(name="老周师傅", attitude="friendly", notes="店主")]
    )
    result = _failed_result(ability="cha", dc=16, total=8)
    events = apply_check_failure_consequences(
        route, result, character, state, user_input=text
    )
    assert state.npcs[0].attitude == "neutral"
    assert any("态度恶化" in event for event in events)


def test_check_failure_stealth_adds_alert():
    text = "潜行穿过巡逻区"
    route = _route(ability="dex")
    character = Character(name="测试", dex=8)
    state = GameState()
    result = _failed_result(ability="dex", dc=15, total=6)
    events = apply_check_failure_consequences(
        route, result, character, state, user_input=text
    )
    assert any("潜行失败" in event for event in events)
    assert any("警戒" in fact for fact in state.memory_facts)


def test_check_failure_does_not_auto_advance_time():
    """时间推进改由 State Agent 判定；检定失败不再机械层自动加时。"""
    route = _route(ability="wis")
    character = Character(name="测试", wisdom=8)
    state = GameState()
    before = state.elapsed_minutes
    result = _failed_result(ability="wis", dc=14, total=5)
    apply_check_failure_consequences(
        route, result, character, state, user_input="观察周围"
    )
    assert state.elapsed_minutes == before


def test_successful_check_has_no_failure_consequences():
    route = _route(ability="wis")
    character = Character(name="测试", wisdom=18)
    state = GameState()
    result = AbilityCheckResult(
        ability="wis",
        dc=5,
        roll=DiceRoll(notation="1d20", rolls=[18], modifier=0, total=18),
        check_total=18,
        success=True,
    )
    events = apply_check_failure_consequences(
        route, result, character, state, user_input="观察周围"
    )
    assert events == []


def test_narrative_brief_includes_failure_constraints():
    route = _route()
    brief = build_narrative_brief_static(
        "潜行进去",
        route,
        [
            "【敏捷检定】1d20[5]+0 = 5 vs DC 14 → 失败",
            "⚠️ 潜行失败：对方可能已察觉",
        ],
    )
    assert "【检定失败" in brief
    assert "不得写行动成功" in brief
    assert "【玩家输入】" in brief
    assert format_check_failure_constraints_for_kp([], route) == ""


def test_check_failure_damage_blocked_by_implant_sp():
    text = "偷窃B1层门禁钥匙卡"
    route = _route(ability="dex")
    character = Character(name="里昂", hp=11, max_hp=11, dex=14)
    character.add_inventory_item("骨骼强化涂层", kind="durable", description="已植入")
    item = character.find_inventory_item("骨骼强化涂层")
    item.effects = EntityEffects(sp=22, sp_max=22)
    character.equip_item("骨骼强化涂层", slot="body")
    state = GameState()
    result = _failed_result(ability="dex", dc=14, total=4)
    events = apply_check_failure_consequences(
        route, result, character, state, user_input=text
    )
    assert character.hp == 11
    assert any("完全挡住" in event for event in events)
    assert not any("💔" in event for event in events)


def test_is_dangerous_attempt():
    assert is_dangerous_attempt("攀爬排水管", _route())
    assert is_social_attempt("说服守卫放行", _route())
