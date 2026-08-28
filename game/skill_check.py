"""属性检定上的技能加值。"""

from __future__ import annotations

from game.models import Character
from game.results import ActionRouteResult

# 主动使用已掌握技能（skill_usage=use 且技能匹配）
SKILL_BONUS_ACTIVE = 4
# 检定与已掌握技能相关但未明确「施展技能」
SKILL_BONUS_RELATED = 2


def skill_bonus_for_route(
    character: Character,
    route: ActionRouteResult | None,
) -> int:
    if route is None or not route.referenced_skills:
        return 0

    matched = [skill for skill in route.referenced_skills if character.has_skill(skill)]
    if not matched:
        return 0

    if route.skill_usage == "use":
        return SKILL_BONUS_ACTIVE
    return SKILL_BONUS_RELATED


def max_ability_check_total(
    *,
    ability_modifier: int = 4,
    proficiency: bool = True,
    skill_bonus: int = SKILL_BONUS_ACTIVE,
) -> int:
    """1d20 满点时的检定总和上限（用于文档/测试）。"""
    prof = 2 if proficiency else 0
    return 20 + ability_modifier + prof + skill_bonus
