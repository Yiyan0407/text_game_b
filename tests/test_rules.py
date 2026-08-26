import pytest

from game.models import Character
from game.rules import ability_check, format_check_for_kp


def test_ability_check_returns_result():
    character = Character(name="测试", strength=14, dex=12, intelligence=10)
    result = ability_check(character, "str", dc=10)
    assert result.ability == "str"
    assert result.dc == 10
    assert len(result.roll.rolls) == 1
    assert result.roll.total == result.roll.rolls[0] + character.modifier("str")
    assert result.success == (result.roll.total >= 10)


def test_ability_check_invalid_ability():
    character = Character(name="测试")
    with pytest.raises(ValueError, match="未知属性"):
        ability_check(character, "luck", dc=10)


def test_ability_check_wisdom():
    character = Character(name="测试", wisdom=14)
    result = ability_check(character, "wis", dc=12)
    assert result.ability == "wis"
    assert result.success == (result.roll.total >= 12)


def test_ability_check_modifier_applied():
    character = Character(name="测试", strength=16)  # mod +3
    result = ability_check(character, "str", dc=20)
    raw = result.roll.rolls[0]
    assert result.roll.total == raw + 3


def test_format_check_for_kp():
    character = Character(name="测试", dex=14)
    result = ability_check(character, "dex", dc=14)
    text = format_check_for_kp(result, character)
    assert "敏捷检定" in text
    assert "DC 14" in text
