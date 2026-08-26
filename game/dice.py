import random
import re

from game.models import DiceRoll

_DICE_PATTERN = re.compile(
    r"^(?:(?P<count>\d+)d(?P<sides>\d+)|d(?P<sides_only>\d+))(?:\s*(?P<sign>[+-])\s*(?P<mod>\d+))?$",
    re.IGNORECASE,
)


def normalize_dice_notation(notation: str) -> str:
    """规范化骰子表达式，兼容 KP 常见误写（如 100 → d100）。"""
    cleaned = notation.strip().lower().replace(" ", "")
    if not cleaned:
        raise ValueError("骰子表达式不能为空")

    if cleaned.isdigit():
        sides = int(cleaned)
        if sides < 2:
            raise ValueError(f"无效的面数: {notation}")
        return f"d{sides}"

    return cleaned


def parse_dice(notation: str) -> tuple[int, int, int]:
    """解析骰子表达式，返回 (颗数, 面数, 修正值)。"""
    cleaned = normalize_dice_notation(notation)
    match = _DICE_PATTERN.match(cleaned)
    if not match:
        raise ValueError(f"无法解析骰子表达式: {notation}")

    count = int(match.group("count") or 1)
    sides = int(match.group("sides") or match.group("sides_only"))
    modifier = int(match.group("mod") or 0)
    if match.group("sign") == "-":
        modifier = -modifier

    if count < 1 or sides < 2:
        raise ValueError(f"无效的骰子参数: {notation}")

    return count, sides, modifier


def roll(notation: str) -> DiceRoll:
    """掷骰并返回结构化结果。"""
    count, sides, modifier = parse_dice(notation)
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier
    return DiceRoll(
        notation=normalize_dice_notation(notation),
        rolls=rolls,
        modifier=modifier,
        total=total,
    )


def roll_4d6_drop_lowest() -> tuple[int, tuple[int, ...], int]:
    """4d6 去掉最低一颗，返回 (总和, 四颗骰点, 被去掉的点数)。"""
    rolls = tuple(random.randint(1, 6) for _ in range(4))
    dropped = min(rolls)
    score = sum(rolls) - dropped
    return score, rolls, dropped


def roll_notation_label(notation: str) -> str:
    count, sides, modifier = parse_dice(notation)
    base = f"{count}d{sides}" if count > 1 else f"d{sides}"
    if modifier > 0:
        return f"{base}+{modifier}"
    if modifier < 0:
        return f"{base}{modifier}"
    return base
