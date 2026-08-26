from game.dice import roll
from game.models import ABILITY_FIELDS, ABILITY_LABELS, Character, DiceRoll
from game.results import AbilityCheckResult


def ability_check(character: Character, ability: str, dc: int) -> AbilityCheckResult:
    """属性检定：1d20 + 属性修正 vs DC。"""
    key = ability.lower()
    if key not in ABILITY_FIELDS:
        allowed = " / ".join(ABILITY_FIELDS)
        raise ValueError(f"未知属性: {ability}，请使用 {allowed}")

    if dc < 1:
        raise ValueError(f"无效的 DC: {dc}")

    modifier = character.modifier(key)
    dice = roll(f"1d20{modifier:+d}")
    success = dice.total >= dc
    return AbilityCheckResult(
        ability=key,
        dc=dc,
        roll=dice,
        success=success,
    )


def format_check_for_kp(result: AbilityCheckResult, character: Character) -> str:
    label = ABILITY_LABELS.get(result.ability, result.ability.upper())
    mod = character.modifier(result.ability)
    outcome = "成功" if result.success else "失败"
    return (
        f"【{label}检定】1d20[{result.roll.rolls[0]}]{mod:+d} = {result.roll.total} "
        f"vs DC {result.dc} → {outcome}"
    )
