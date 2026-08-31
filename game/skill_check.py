"""属性检定上的技能加值（主动施展 + 被动常驻）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from game.models import ABILITY_FIELDS, Character
from game.results import ActionRouteResult
from game.skills import Skill
from game.text_match import fuzzy_match_name

# 主动使用已掌握技能（skill_usage=use 且技能匹配）
SKILL_BONUS_ACTIVE = 4
# 检定与已掌握主动技能相关但未明确「施展技能」
SKILL_BONUS_RELATED = 2
# 每个相关被动技能
PASSIVE_SKILL_BONUS = 2
# 单轮检定被动加值上限（每项被动 +2）
MAX_PASSIVE_SKILL_BONUS = 6

_ABILITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "str": ("力量", "强壮", "蛮力", "破门", "举重", "搏击", "近战"),
    "dex": ("敏捷", "灵活", "潜行", "闪避", "平衡", "体操", "偷窃"),
    "con": (
        "体质",
        "生命",
        "耐力",
        "基因",
        "改造",
        "血脉",
        "神选",
        "强化",
        "再生",
        "抗毒",
        "耐受",
    ),
    "int": ("智力", "分析", "黑客", "逻辑", "记忆", "计算", "破解", "科研"),
    "wis": ("感知", "察觉", "直觉", "祝福", "神启", "警觉", "洞察", "追踪", "诅咒", "恶咒"),
    "cha": ("魅力", "说服", "交涉", "恶魔契约", "蛊惑", "领导", "表演", "诅咒", "代价"),
}

_CURSE_MARKERS: tuple[str, ...] = (
    "诅咒",
    "恶咒",
    "代价",
    "侵蚀",
    "反噬",
    "虚弱",
    "诅咒",
    "debilit",
    "curse",
)


@dataclass
class SkillBonusBreakdown:
    active: int = 0
    passive: int = 0
    passive_skills: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.active + self.passive


def compute_skill_bonus(
    character: Character,
    route: ActionRouteResult | None,
    *,
    ability: str = "",
    user_input: str = "",
) -> SkillBonusBreakdown:
    """主动技能加值 + 相关被动技能自动加值。"""
    active = _active_skill_bonus(character, route)
    passive, names = _passive_skill_bonus_for_check(
        character,
        ability=ability,
        user_input=user_input,
        route=route,
    )
    return SkillBonusBreakdown(active=active, passive=passive, passive_skills=names)


def skill_bonus_for_route(
    character: Character,
    route: ActionRouteResult | None,
    *,
    ability: str = "",
    user_input: str = "",
) -> int:
    return compute_skill_bonus(
        character,
        route,
        ability=ability,
        user_input=user_input,
    ).total


def _active_skill_bonus(
    character: Character,
    route: ActionRouteResult | None,
) -> int:
    if route is None or not route.referenced_skills:
        return 0

    matched = [
        name
        for name in route.referenced_skills
        if character.has_skill(name)
        and (skill := character.find_skill(name))
        and skill.kind != "passive"
    ]
    if not matched:
        return 0

    if route.skill_usage == "use":
        return SKILL_BONUS_ACTIVE
    return SKILL_BONUS_RELATED


def _passive_skill_bonus_for_check(
    character: Character,
    *,
    ability: str,
    user_input: str = "",
    route: ActionRouteResult | None = None,
) -> tuple[int, list[str]]:
    ability_key = ability.strip().lower()
    if ability_key not in ABILITY_FIELDS:
        return 0, []

    matched: list[str] = []
    total = 0
    for skill in character.passive_skills():
        if _passive_skill_applies(skill, ability_key, user_input, route):
            matched.append(skill.name)
            total += _check_bonus_for_passive(skill)

    if not matched:
        return 0, []

    capped = max(-MAX_PASSIVE_SKILL_BONUS, min(MAX_PASSIVE_SKILL_BONUS, total))
    return capped, matched


def _check_bonus_for_passive(skill: Skill) -> int:
    effects = skill.effects
    if effects is not None and effects.check_bonus != 0:
        return effects.check_bonus
    if effects is not None and (effects.max_hp_bonus < 0 or effects.ac_bonus < 0):
        return -PASSIVE_SKILL_BONUS
    if _is_curse_like(skill):
        return -PASSIVE_SKILL_BONUS
    return PASSIVE_SKILL_BONUS


def _is_curse_like(skill: Skill) -> bool:
    blob = f"{skill.name} {skill.description}".casefold()
    return any(marker.casefold() in blob for marker in _CURSE_MARKERS)


def _passive_skill_applies(
    skill: Skill,
    ability: str,
    user_input: str,
    route: ActionRouteResult | None,
) -> bool:
    if skill.name and user_input and fuzzy_match_name(skill.name, user_input):
        return True

    if route and route.referenced_skills:
        for ref in route.referenced_skills:
            if fuzzy_match_name(ref, skill.name):
                return True

    related = _related_abilities_for_passive(skill)
    if related:
        return ability in related or "all" in related

    skill_blob = f"{skill.name} {skill.description}".strip()
    return _infer_ability_from_text(skill_blob, ability)


def _related_abilities_for_passive(skill: Skill) -> set[str]:
    if skill.effects is None:
        return set()
    raw = getattr(skill.effects, "related_abilities", None) or []
    normalized: set[str] = set()
    for entry in raw:
        key = str(entry).strip().lower()
        if key in ABILITY_FIELDS:
            normalized.add(key)
        elif key in ("all", "任意", "全部"):
            normalized.add("all")
    return normalized


def _infer_ability_from_text(text: str, ability: str) -> bool:
    lowered = text.casefold()
    keywords = _ABILITY_KEYWORDS.get(ability, ())
    return any(keyword.casefold() in lowered for keyword in keywords)


def format_passive_skills_for_kp(character: Character) -> str:
    """供 KP 叙事简报：列出被动技能及其自动检定加成说明。"""
    passive = character.passive_skills()
    if not passive:
        return ""

    lines = [
        "【被动技能 — 常驻生效】",
        "以下能力无需玩家「施展」；相关检定时系统自动加减值（见【已发生的结果】，可为负）。",
        "叙事须体现祝福/改造/诅咒/契约的代价或增益，勿写玩家未拥有的能力。",
    ]
    for skill in passive:
        related = _related_abilities_for_passive(skill)
        if related and "all" not in related:
            labels = "/".join(k.upper() for k in sorted(related))
            scope = f"相关检定：{labels}"
        elif related:
            scope = "相关检定：全属性"
        else:
            scope = "相关检定：按名称/描述语义自动匹配"
        check = _check_bonus_for_passive(skill)
        sign = "+" if check > 0 else ""
        detail = skill.description.strip() or "（无说明）"
        effect_bits: list[str] = [f"检定{sign}{check}"]
        if skill.effects:
            summary = skill.effects.format_summary()
            if summary:
                effect_bits.append(summary)
        lines.append(f"- {skill.name}（{scope}；{' · '.join(effect_bits)}）— {detail}")
    return "\n".join(lines)


def max_ability_check_total(
    *,
    ability_modifier: int = 4,
    proficiency: bool = True,
    skill_bonus: int = SKILL_BONUS_ACTIVE,
) -> int:
    """1d20 满点时的检定总和上限（用于文档/测试）。"""
    prof = 2 if proficiency else 0
    return 20 + ability_modifier + prof + skill_bonus
