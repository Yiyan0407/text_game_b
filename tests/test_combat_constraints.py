from game.combat_constraints import (
    format_combat_start_constraints_for_kp,
    is_combat_start_without_attack_resolution,
)
from game.results import ActionRouteResult


def test_combat_start_turn_detected_without_attack():
    route = ActionRouteResult(trigger_combat=True, combat_action="none")
    events = ["战斗开始！先攻顺序：玩家 → 敌人。", "轮到你行动。"]
    assert is_combat_start_without_attack_resolution(events, route) is True
    text = format_combat_start_constraints_for_kp(events, route)
    assert "开战当回合" in text
    assert "禁止" in text


def test_combat_start_turn_not_detected_after_attack():
    route = ActionRouteResult(mode="combat", combat_action="attack")
    events = ["战斗开始！", "攻击 敌人 → 命中！造成 5 点伤害"]
    assert is_combat_start_without_attack_resolution(events, route) is False
    assert format_combat_start_constraints_for_kp(events, route) == ""
