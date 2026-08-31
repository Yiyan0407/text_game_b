import pytest

from game.character_creation import build_character, roll_ability_scores
from game.dice import roll_4d6_drop_lowest
from game.models import Character, compute_max_hp


def test_roll_4d6_drop_lowest_range():
    for _ in range(50):
        score, rolls, dropped = roll_4d6_drop_lowest()
        assert len(rolls) == 4
        assert dropped == min(rolls)
        assert score == sum(rolls) - dropped
        assert 3 <= score <= 18


def test_roll_ability_scores_has_six_attributes():
    rolled = roll_ability_scores()
    assert len(rolled.details) == 6
    assert rolled.total_score() == sum(d.score for d in rolled.details)


def test_rolled_abilities_total_score():
    rolled = roll_ability_scores()
    assert 18 <= rolled.total_score() <= 108
    fields = rolled.to_character_fields()
    assert set(fields) == {
        "strength",
        "dex",
        "constitution",
        "intelligence",
        "wisdom",
        "charisma",
    }


def test_build_character_sets_hp_from_constitution():
    rolled = roll_ability_scores()
    character = build_character("测试", "背景", rolled)
    expected_hp = compute_max_hp(character.constitution)
    assert character.max_hp == expected_hp
    assert character.hp == expected_hp


def test_build_character_applies_starter_skills():
    rolled = roll_ability_scores()
    character = build_character(
        "测试",
        "一位初到此地的冒险者。",
        rolled,
        starter_skills=["观察（留意细节）", "交涉"],
    )
    assert character.skill_names() == ["观察", "交涉"]
    assert character.skills[0].description == "留意细节"


def test_compute_max_hp_minimum():
    assert compute_max_hp(3) == 8
    assert compute_max_hp(10) == 10
    assert compute_max_hp(16) == 13


def test_character_six_abilities_modifier():
    character = Character(
        name="测试",
        strength=16,
        dex=14,
        constitution=12,
        intelligence=10,
        wisdom=8,
        charisma=18,
    )
    assert character.modifier("str") == 3
    assert character.modifier("wis") == -1
    assert character.modifier("cha") == 4
    assert "感知(WIS)" in character.format_abilities()
