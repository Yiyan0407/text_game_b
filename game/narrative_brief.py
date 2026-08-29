"""叙事简报构建：供 KP 纯叙事模式使用。"""

from game.check_consequences import format_check_failure_constraints_for_kp
from game.combat_constraints import format_combat_constraints_for_kp
from game.models import Character, GameState
from game.narrative_time import format_turn_time_hint
from game.results import ActionRouteResult


def build_narrative_brief_static(
    user_input: str,
    route: ActionRouteResult | None,
    mechanical_events: list[str],
) -> str:
    """构建不含补丁后状态的静态段（可在 StateAgent 等待期间预组装）。"""
    lines: list[str] = ["【叙事简报】"]
    if route is not None:
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
        "【写作要求】第二人称「你」，只写玩家本句请求范围内的事，勿擅自推进未提及的后续情节；"
        "勿复述本简报字段；勿列编号选项。"
        "文笔：具体可感、有画面与气氛，像小说片段而非状态说明；五感与对话优先，机制词勿入文。"
        "叙事须与下方【当前状态】背包、装备、技能一致：【装备·手持】中的武器/工具/手电即已在手上；"
        "【装备·身体】中的防具/穿戴物应体现在叙事中；"
        "**攻击/伤害/治疗/受击须与【已发生的结果】及【伤害约束】完全一致，禁止自编骰点或伤害数字**；"
        "SP 阻挡/磨损/击穿以机械结果为准；检定失败须体现系统已记录的受伤/关系/暴露等后果，"
        "写察觉不足或环境干扰，勿否定玩家持有物，更不可写失败检定却行动成功。"
        "购买/用物/拾取：KP 先写过程与结果，系统会在叙事后结算背包变更。"
    )
    lines.append("")
    lines.append("【玩家输入】")
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
        time_hint = format_turn_time_hint(state_events)
        if time_hint:
            lines.append(time_hint)
    lines.append("")
    lines.append("【叙事时间 — 必须一致，禁止与下列时钟矛盾】")
    lines.append(format_narrative_time_context(game_state))
    constraints = format_time_constraints_for_kp(game_state)
    if constraints:
        lines.append("")
        lines.append(constraints)
    from game.background_process import format_background_processes_for_kp

    process_hint = format_background_processes_for_kp(game_state)
    if process_hint:
        lines.append("")
        lines.append(process_hint)
    lines.append("")
    lines.append("【当前状态】")
    lines.append(f"场景：{game_state.current_scene or '（未知）'}")
    if game_state.npcs:
        npc_text = "；".join(
            f"{npc.name}（{npc.attitude}）" for npc in game_state.npcs[:8]
        )
        lines.append(f"已知 NPC：{npc_text}")
    lines.append(f"背包：{character.format_inventory()}")
    lines.append(f"装备：{character.format_equipment()}")
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
