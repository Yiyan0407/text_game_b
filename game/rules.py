from game.dice import roll
from game.models import ABILITY_FIELDS, ABILITY_LABELS, Character
from game.results import AbilityCheckResult

PROFICIENCY_BONUS = 2


def ability_check(
    character: Character,
    ability: str,
    dc: int,
    *,
    proficiency_bonus: bool = False,
    skill_bonus: int = 0,
    active_skill_bonus: int = 0,
    passive_skill_bonus: int = 0,
    passive_skills_applied: list[str] | None = None,
    situational_bonus: int = 0,
) -> AbilityCheckResult:
    """属性检定：1d20 + 属性修正 + 专业(+2) + 技能加值 vs DC。"""
    key = ability.lower()
    if key not in ABILITY_FIELDS:
        allowed = " / ".join(ABILITY_FIELDS)
        raise ValueError(f"未知属性: {ability}，请使用 {allowed}")

    if dc < 1:
        raise ValueError(f"无效的 DC: {dc}")

    modifier = character.modifier(key)
    prof = PROFICIENCY_BONUS if proficiency_bonus else 0
    active = int(active_skill_bonus)
    passive = int(passive_skill_bonus)
    if skill_bonus:
        skill_total = int(skill_bonus)
    else:
        skill_total = active + passive
    skill_total = max(-20, min(20, skill_total))
    situational = int(situational_bonus)
    applied_passive = list(passive_skills_applied or [])
    dice = roll(f"1d20{modifier:+d}")
    check_total = dice.total + prof + skill_total + situational
    success = check_total >= dc
    return AbilityCheckResult(
        ability=key,
        dc=dc,
        roll=dice,
        proficiency_bonus=prof,
        skill_bonus=skill_total,
        active_skill_bonus=active,
        passive_skill_bonus=passive,
        passive_skills_applied=applied_passive,
        situational_bonus=situational,
        check_total=check_total,
        success=success,
    )


def format_check_for_kp(result: AbilityCheckResult, character: Character) -> str:
    label = ABILITY_LABELS.get(result.ability, result.ability.upper())
    mod = character.modifier(result.ability)
    outcome = "成功" if result.success else "失败"
    bonus = f"{mod:+d}"
    if result.proficiency_bonus:
        bonus += f"+{result.proficiency_bonus}专业"
    if result.active_skill_bonus:
        bonus += f"+{result.active_skill_bonus}主动"
    if result.passive_skill_bonus != 0:
        names = "、".join(result.passive_skills_applied) or "被动"
        sign = "+" if result.passive_skill_bonus > 0 else ""
        bonus += f"{sign}{result.passive_skill_bonus}被动({names})"
    elif result.skill_bonus and not result.active_skill_bonus:
        bonus += f"+{result.skill_bonus}技能"
    if result.situational_bonus:
        bonus += f"+{result.situational_bonus}环境"
    return (
        f"【{label}检定】1d20[{result.roll.rolls[0]}]{bonus} "
        f"= {result.check_total} vs DC {result.dc} → {outcome}"
    )
