"""叙事简报构建：供 KP 纯叙事模式使用。"""

from game.check_consequences import format_check_failure_constraints_for_kp
from game.combat_constraints import format_combat_constraints_for_kp
from game.models import Character, GameState
from game.results import ActionRouteResult


def build_narrative_brief_static(
    user_input: str,
    route: ActionRouteResult | None,
    mechanical_events: list[str],
) -> str:
    """构建不含补丁后状态的静态段（可在 StateAgent 等待期间预组装）。"""
    lines: list[str] = ["【叙事简报】"]
    if route is not None:
        lines.append(f"【本轮行动】{route.action_intent}")
        lines.append(f"【叙事收笔】{route.scope_stop}")
        if route.must_not_narrate:
            lines.append("【禁止推进】")
            for item in route.must_not_narrate:
                lines.append(f"- {item}")
        in_combat = route.mode == "combat" or route.trigger_combat
        if in_combat:
            lines.append("【模式】战斗 — 根据机械结果叙事，勿编骰点。")
        else:
            lines.append("【模式】探索 — 根据机械结果叙事，勿编骰点。")
    if mechanical_events:
        lines.append("【已发生的结果】")
        for event in mechanical_events:
            lines.append(f"- {event}")
    else:
        lines.append("【已发生的结果】（无机械结算，直接叙事）")
    failure_constraints = format_check_failure_constraints_for_kp(mechanical_events, route)
    if failure_constraints:
        lines.append("")
        lines.append(failure_constraints)
    combat_constraints = format_combat_constraints_for_kp(mechanical_events, route)
    if combat_constraints:
        lines.append("")
        lines.append(combat_constraints)
    lines.append(
        "【写作要求】第二人称「你」，遵守叙事收笔与禁止推进；勿复述本简报字段；勿列编号选项。"
        "叙事须与下方【当前状态】背包、持用、技能一致：已有照明/工具时不可写「没有照明」；"
        "【持用】中的物品应体现在叙事中；检定失败须体现系统已记录的受伤/关系/暴露等后果，"
        "写察觉不足或环境干扰，勿否定玩家持有物，更不可写失败检定却行动成功。"
    )
    lines.append("")
    lines.append(user_input.strip())
    return "\n".join(lines)


def merge_narrative_brief_with_state(
    brief_static: str,
    character: Character,
    game_state: GameState,
    state_events: list[str] | None = None,
) -> str:
    """合并补丁应用后的状态快照。"""
    from game.narrative_time import (
        format_narrative_time_context,
        format_time_constraints_for_kp,
    )

    lines = [brief_static.rstrip()]
    if state_events:
        lines.append("")
        lines.append("【状态同步事件】")
        for event in state_events:
            lines.append(f"- {event}")
    lines.append("")
    lines.append("【叙事时间 — 必须一致，禁止与下列时钟矛盾】")
    lines.append(format_narrative_time_context(game_state))
    constraints = format_time_constraints_for_kp(game_state)
    if constraints:
        lines.append("")
        lines.append(constraints)
    lines.append("")
    lines.append("【当前状态】")
    lines.append(f"场景：{game_state.current_scene or '（未知）'}")
    if game_state.npcs:
        npc_text = "；".join(
            f"{npc.name}（{npc.attitude}）" for npc in game_state.npcs[:8]
        )
        lines.append(f"已知 NPC：{npc_text}")
    lines.append(f"背包：{character.format_inventory()}")
    lines.append(f"持用：{character.format_active_gear()}")
    lines.append(f"技能：{character.format_skills()}")
    return "\n".join(lines)


def build_narrative_brief(
    user_input: str,
    route: ActionRouteResult | None,
    mechanical_events: list[str],
    character: Character,
    game_state: GameState,
    state_events: list[str] | None = None,
) -> str:
    """一次性构建完整叙事简报。"""
    static = build_narrative_brief_static(user_input, route, mechanical_events)
    return merge_narrative_brief_with_state(static, character, game_state, state_events)
