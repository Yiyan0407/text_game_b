from game.models import Character
from game.results import ActionRouteResult
from game.rules import ability_check, format_check_for_kp
from game.skills import Skill
from game.skill_check import (
    PASSIVE_SKILL_BONUS,
    SKILL_BONUS_ACTIVE,
    SKILL_BONUS_RELATED,
    compute_skill_bonus,
    max_ability_check_total,
    skill_bonus_for_route,
)


def test_skill_bonus_for_active_use():
    character = Character(name="测试", skills=["潜行"])
    route = ActionRouteResult(
        approved=True,
        skill_usage="use",
        referenced_skills=["潜行"],
    )
    assert skill_bonus_for_route(character, route) == SKILL_BONUS_ACTIVE


def test_skill_bonus_for_related_only():
    character = Character(name="测试", skills=["急救"])
    route = ActionRouteResult(
        approved=True,
        referenced_skills=["急救"],
    )
    assert skill_bonus_for_route(character, route) == SKILL_BONUS_RELATED


def test_skill_bonus_zero_without_skill():
    character = Character(name="测试", skills=["潜行"])
    route = ActionRouteResult(
        approved=True,
        skill_usage="use",
        referenced_skills=["黑客入侵"],
    )
    assert skill_bonus_for_route(character, route) == 0


def test_ability_check_can_reach_dc_30():
    character = Character(name="测试", dex=18, skills=["潜行"])
    result = ability_check(
        character,
        "dex",
        dc=30,
        proficiency_bonus=True,
        skill_bonus=SKILL_BONUS_ACTIVE,
    )
    assert result.check_total == result.roll.total + 2 + 4
    if result.roll.rolls[0] == 20:
        assert result.success is True


def test_max_ability_check_total():
    assert max_ability_check_total() == 30


def test_format_check_shows_skill_bonus():
    character = Character(name="测试", dex=14, skills=["潜行"])
    result = ability_check(
        character,
        "dex",
        dc=14,
        active_skill_bonus=SKILL_BONUS_ACTIVE,
    )
    text = format_check_for_kp(result, character)
    assert "+4主动" in text


def test_passive_skill_auto_applies_on_relevant_con_check():
    character = Character(
        name="测试",
        skills=[Skill(name="基因改造", kind="passive", description="强化体质")],
    )
    route = ActionRouteResult(approved=True, ability="con", roll_type="ability_check")
    bd = compute_skill_bonus(
        character,
        route,
        ability="con",
        user_input="忍痛坚持",
    )
    assert bd.passive == PASSIVE_SKILL_BONUS
    assert bd.passive_skills == ["基因改造"]


def test_passive_skill_not_applied_on_unrelated_ability():
    character = Character(
        name="测试",
        skills=[Skill(name="基因改造", kind="passive", description="强化体质")],
    )
    route = ActionRouteResult(approved=True, ability="int", roll_type="ability_check")
    bd = compute_skill_bonus(character, route, ability="int", user_input="破解终端")
    assert bd.passive == 0


def test_passive_skill_uses_related_abilities_from_effects():
    from game.effects import EntityEffects

    character = Character(
        name="测试",
        skills=[
            Skill(
                name="神选",
                kind="passive",
                description="直觉敏锐",
                effects=EntityEffects(related_abilities=["wis"], forged=True),
            )
        ],
    )
    route = ActionRouteResult(approved=True, ability="wis", roll_type="ability_check")
    bd = compute_skill_bonus(character, route, ability="wis", user_input="观察周围")
    assert bd.passive == PASSIVE_SKILL_BONUS


def test_format_check_shows_passive_skill_names():
    character = Character(name="测试", constitution=14)
    result = ability_check(
        character,
        "con",
        dc=12,
        passive_skill_bonus=2,
        passive_skills_applied=["基因改造"],
    )
    text = format_check_for_kp(result, character)
    assert "+2被动(基因改造)" in text
