from game.models import Character
from game.results import ActionRouteResult
from game.rules import ability_check, format_check_for_kp
from game.skill_check import (
    SKILL_BONUS_ACTIVE,
    SKILL_BONUS_RELATED,
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
        skill_bonus=SKILL_BONUS_ACTIVE,
    )
    text = format_check_for_kp(result, character)
    assert "+4技能" in text
