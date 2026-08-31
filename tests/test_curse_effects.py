"""诅咒/代价技能：负向数值与检定减值。"""

from game.effect_validate import validate_effects
from game.effects import EntityEffects
from game.models import Character
from game.results import ActionRouteResult
from game.rules import ability_check, format_check_for_kp
from game.skill_check import PASSIVE_SKILL_BONUS, compute_skill_bonus
from game.skills import Skill


def test_validate_effects_allows_negative_max_hp_and_check_bonus():
    effects = validate_effects(
        EntityEffects(max_hp_bonus=-8, ac_bonus=-1, check_bonus=-2, forged=True)
    )
    assert effects.max_hp_bonus == -8
    assert effects.ac_bonus == -1
    assert effects.check_bonus == -2


def test_curse_passive_reduces_effective_max_hp():
    character = Character(name="测试", max_hp=20, hp=20)
    character.skills.append(
        Skill(
            name="古神诅咒",
            kind="passive",
            description="侵蚀生命",
            effects=EntityEffects(max_hp_bonus=-6, forged=True),
        )
    )
    assert character.effective_max_hp() == 14


def test_curse_passive_auto_penalty_on_relevant_check():
    character = Character(
        name="测试",
        skills=[
            Skill(
                name="古神诅咒",
                kind="passive",
                description="低语侵蚀",
                effects=EntityEffects(
                    check_bonus=-2,
                    related_abilities=["wis"],
                    forged=True,
                ),
            )
        ],
    )
    route = ActionRouteResult(approved=True, ability="wis", roll_type="ability_check")
    bd = compute_skill_bonus(character, route, ability="wis", user_input="辨别真伪")
    assert bd.passive == -2
    assert bd.passive_skills == ["古神诅咒"]


def test_curse_inferred_negative_check_without_explicit_check_bonus():
    character = Character(
        name="测试",
        skills=[Skill(name="恶咒缠身", kind="passive", description="行动迟缓")],
    )
    route = ActionRouteResult(approved=True, ability="wis", roll_type="ability_check")
    bd = compute_skill_bonus(character, route, ability="wis", user_input="观察")
    assert bd.passive == -PASSIVE_SKILL_BONUS


def test_format_summary_shows_negative_values():
    summary = EntityEffects(
        max_hp_bonus=-5,
        ac_bonus=-1,
        check_bonus=-2,
        forged=True,
    ).format_summary()
    assert "HP-5" in summary
    assert "AC-1" in summary
    assert "检定-2" in summary


def test_format_check_shows_negative_passive_bonus():
    character = Character(name="测试", wisdom=12)
    result = ability_check(
        character,
        "wis",
        dc=14,
        passive_skill_bonus=-2,
        passive_skills_applied=["古神诅咒"],
    )
    text = format_check_for_kp(result, character)
    assert "-2被动(古神诅咒)" in text


def test_effective_max_hp_floors_at_one():
    character = Character(name="测试", max_hp=5, hp=5)
    character.skills.append(
        Skill(
            name="致命诅咒",
            kind="passive",
            effects=EntityEffects(max_hp_bonus=-20, forged=True),
        )
    )
    assert character.effective_max_hp() == 1
