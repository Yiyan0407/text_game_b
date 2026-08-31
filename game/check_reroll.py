"""检定申诉与重掷：KP meta 撤销误判失败并授予重掷。"""

from __future__ import annotations

from game.models import ABILITY_LABELS, Character, GameState, LastAbilityCheckRecord, PendingReroll
from game.results import RerollPatch
from game.text_match import fuzzy_match_name


def _reroll_applies_to_action(
    pending: PendingReroll,
    game_state: GameState,
    user_input: str,
) -> bool:
    """待重掷仅可套用于玩家重试同一申诉行动，不可用于无关检定。"""
    current = user_input.strip()
    if not current:
        return False

    hints: list[str] = []
    if pending.action_hint.strip():
        hints.append(pending.action_hint.strip())
    last = game_state.last_ability_check
    if last:
        if last.user_input.strip():
            hints.append(last.user_input.strip())
        if last.action_intent.strip():
            hints.append(last.action_intent.strip())

    if not hints:
        return False

    for hint in hints:
        if fuzzy_match_name(hint, current) or fuzzy_match_name(current, hint):
            return True
        if len(hint) >= 4 and hint in current:
            return True
        if len(current) >= 4 and current in hint:
            return True
    return False


def record_ability_check(
    game_state: GameState,
    *,
    character: Character,
    ability: str,
    dc: int,
    check_total: int,
    roll_total: int,
    success: bool,
    action_intent: str,
    user_input: str,
    proficiency_bonus: bool,
    hp_before: int,
) -> None:
    game_state.last_ability_check = LastAbilityCheckRecord(
        ability=ability.strip().lower(),
        dc=int(dc),
        check_total=int(check_total),
        roll_total=int(roll_total),
        success=bool(success),
        action_intent=action_intent.strip(),
        user_input=user_input.strip(),
        proficiency_bonus=bool(proficiency_bonus),
        hp_before=int(hp_before),
        hp_after=int(character.hp),
    )


def apply_pending_reroll_to_route(
    route,
    game_state: GameState,
    *,
    user_input: str = "",
) -> list[str]:
    """若存在 KP 授予的重掷，覆盖 DC 并消耗一次机会（须与申诉行动一致）。"""
    pending = game_state.pending_reroll
    if pending is None:
        return []
    if not route.needs_roll or route.roll_type != "ability_check":
        return []

    if not _reroll_applies_to_action(pending, game_state, user_input):
        game_state.pending_reroll = None
        return []

    events: list[str] = []
    if pending.adjusted_dc > 0:
        old_dc = route.dc
        route.dc = pending.adjusted_dc
        events.append(
            f"🔄 KP 裁定重掷：DC {old_dc} → {pending.adjusted_dc}"
            + (f"（{pending.reason}）" if pending.reason.strip() else "")
        )
    else:
        events.append(
            "🔄 KP 裁定重掷"
            + (f"：{pending.reason}" if pending.reason.strip() else "")
        )

    if pending.ability.strip() and not route.ability.strip():
        route.ability = pending.ability.strip()

    game_state.pending_reroll = None
    return events


def apply_reroll_patch(
    patch: RerollPatch,
    character: Character,
    game_state: GameState,
) -> list[str]:
    """应用 KP meta 的检定申诉 patch。"""
    if not patch.grant and not patch.overturn_failure:
        return []

    events: list[str] = []
    last = game_state.last_ability_check

    if patch.overturn_failure:
        if last is None or last.success:
            events.append("跳过检定撤销：无最近失败检定可撤销。")
        else:
            if last.hp_after < last.hp_before and character.hp < last.hp_before:
                before = character.hp
                cap = character.effective_max_hp()
                character.hp = min(cap, last.hp_before)
                if character.hp != before:
                    events.append(
                        f"↩️ 撤销检定伤害：HP {before} → {character.hp}/{cap}"
                    )
            ability_label = ABILITY_LABELS.get(last.ability, last.ability.upper())
            events.append(
                f"↩️ 撤销检定失败：{ability_label} {last.check_total} vs DC {last.dc} 不作数"
            )
            game_state.last_ability_check = None

    if patch.grant:
        dc = patch.adjusted_dc
        if dc <= 0 and last is not None:
            dc = last.dc
        ability = patch.ability.strip() or (last.ability if last else "")
        hint = patch.action_hint.strip() or (last.action_intent if last else "")
        game_state.pending_reroll = PendingReroll(
            adjusted_dc=max(0, int(dc)),
            ability=ability,
            action_hint=hint,
            reason=patch.reason.strip(),
        )
        detail = f"DC {dc}" if dc > 0 else "原 DC"
        events.append(f"🎲 授予重掷：请重新发送上一轮行动（{detail}）")

    return events


def format_last_check_for_prompt(game_state: GameState) -> str:
    last = game_state.last_ability_check
    if last is None:
        return "（无）"
    ability_label = ABILITY_LABELS.get(last.ability, last.ability.upper())
    outcome = "成功" if last.success else "失败"
    lines = [
        f"- {ability_label} 检定：{last.check_total} vs DC {last.dc} → {outcome}",
        f"- 行动：{last.action_intent or '（未记录）'}",
    ]
    if last.hp_after < last.hp_before:
        lines.append(f"- 失败后果：HP {last.hp_before} → {last.hp_after}")
    if game_state.pending_reroll is not None:
        pr = game_state.pending_reroll
        lines.append(
            f"- 待重掷：DC {pr.adjusted_dc or '（沿用路由）'}"
            + (f"，{pr.action_hint}" if pr.action_hint else "")
        )
    return "\n".join(lines)
