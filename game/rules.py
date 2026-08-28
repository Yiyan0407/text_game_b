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
    skill = max(0, int(skill_bonus))
    dice = roll(f"1d20{modifier:+d}")
    check_total = dice.total + prof + skill
    success = check_total >= dc
    return AbilityCheckResult(
        ability=key,
        dc=dc,
        roll=dice,
        proficiency_bonus=prof,
        skill_bonus=skill,
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
    if result.skill_bonus:
        bonus += f"+{result.skill_bonus}技能"
    return (
        f"【{label}检定】1d20[{result.roll.rolls[0]}]{bonus} "
        f"= {result.check_total} vs DC {result.dc} → {outcome}"
    )
