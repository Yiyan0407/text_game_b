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
    route = _route(action_intent="悄悄潜入仓库后门")
    assert is_stealth_attempt(route)


def test_check_failure_records_memory_and_damage():
    route = _route(action_intent="攀爬破损外墙进入二楼", ability="dex")
    character = Character(name="测试", hp=20, max_hp=20, dex=8)
    state = GameState()
    result = _failed_result(ability="dex", dc=18, total=7)
    events = apply_check_failure_consequences(route, result, character, state)
    assert any("行动失败" in event for event in events)
    assert any("受到" in event or "伤害" in event for event in events)
    assert character.hp < 20
    assert any("攀爬" in fact for fact in state.memory_facts)


def test_check_failure_social_worsens_npc_attitude():
    route = _route(action_intent="向老周师傅求情", ability="cha")
    character = Character(name="测试", cha=8)
    state = GameState(
        npcs=[NPCRelation(name="老周师傅", attitude="friendly", notes="店主")]
    )
    result = _failed_result(ability="cha", dc=16, total=8)
    events = apply_check_failure_consequences(route, result, character, state)
    assert state.npcs[0].attitude == "neutral"
    assert any("态度恶化" in event for event in events)


def test_check_failure_stealth_adds_alert():
    route = _route(action_intent="潜行穿过巡逻区", ability="dex")
    character = Character(name="测试", dex=8)
    state = GameState()
    result = _failed_result(ability="dex", dc=15, total=6)
    events = apply_check_failure_consequences(route, result, character, state)
    assert any("潜行失败" in event for event in events)
    assert any("警戒" in fact for fact in state.memory_facts)


def test_check_failure_does_not_auto_advance_time():
    """时间推进改由 State Agent 判定；检定失败不再机械层自动加时。"""
    route = _route(action_intent="观察周围", ability="wis")
    character = Character(name="测试", wisdom=8)
    state = GameState()
    before = state.elapsed_minutes
    result = _failed_result(ability="wis", dc=14, total=5)
    apply_check_failure_consequences(route, result, character, state)
    assert state.elapsed_minutes == before


def test_successful_check_has_no_failure_consequences():
    route = _route(action_intent="观察周围", ability="wis")
    character = Character(name="测试", wisdom=18)
    state = GameState()
    result = AbilityCheckResult(
        ability="wis",
        dc=5,
        roll=DiceRoll(notation="1d20", rolls=[18], modifier=0, total=18),
        check_total=18,
        success=True,
    )
    events = apply_check_failure_consequences(route, result, character, state)
    assert events == []


def test_narrative_brief_includes_failure_constraints():
    route = _route(action_intent="潜行进入", scope_stop="仍停留在门外")
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
    assert format_check_failure_constraints_for_kp([], route) == ""


def test_check_failure_damage_blocked_by_implant_sp():
    route = _route(action_intent="偷窃B1层门禁钥匙卡", ability="dex")
    character = Character(name="里昂", hp=11, max_hp=11, dex=14)
    character.add_inventory_item("骨骼强化涂层", kind="durable", description="已植入")
    item = character.find_inventory_item("骨骼强化涂层")
    item.effects = EntityEffects(sp=22, sp_max=22)
    character.equip_item("骨骼强化涂层", slot="body")
    state = GameState()
    result = _failed_result(ability="dex", dc=14, total=4)
    events = apply_check_failure_consequences(route, result, character, state)
    assert character.hp == 11
    assert any("完全挡住" in event for event in events)
    assert not any("💔" in event for event in events)


def test_is_dangerous_attempt():
    assert is_dangerous_attempt(_route(action_intent="攀爬排水管"))
    assert is_social_attempt(_route(action_intent="说服守卫放行"))
