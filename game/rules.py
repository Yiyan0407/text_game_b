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
) -> AbilityCheckResult:
    """属性检定：1d20 + 属性修正 (+ 专业加值) vs DC。"""
    key = ability.lower()
    if key not in ABILITY_FIELDS:
        allowed = " / ".join(ABILITY_FIELDS)
        raise ValueError(f"未知属性: {ability}，请使用 {allowed}")

    if dc < 1:
        raise ValueError(f"无效的 DC: {dc}")

    modifier = character.modifier(key)
    prof = PROFICIENCY_BONUS if proficiency_bonus else 0
    dice = roll(f"1d20{modifier:+d}")
    check_total = dice.total + prof
    success = check_total >= dc
    return AbilityCheckResult(
        ability=key,
        dc=dc,
        roll=dice,
        proficiency_bonus=prof,
        check_total=check_total,
        success=success,
    )


def format_check_for_kp(result: AbilityCheckResult, character: Character) -> str:
    label = ABILITY_LABELS.get(result.ability, result.ability.upper())
    mod = character.modifier(result.ability)
    outcome = "成功" if result.success else "失败"
    prof_part = f"+{result.proficiency_bonus}专业" if result.proficiency_bonus else ""
    return (
        f"【{label}检定】1d20[{result.roll.rolls[0]}]{mod:+d}{prof_part} "
        f"= {result.check_total} vs DC {result.dc} → {outcome}"
    )
