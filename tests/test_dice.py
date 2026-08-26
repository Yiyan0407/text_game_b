import pytest

from game.dice import parse_dice, roll


def test_parse_d20():
    assert parse_dice("d20") == (1, 20, 0)


def test_parse_2d6():
    assert parse_dice("2d6") == (2, 6, 0)


def test_parse_with_modifier():
    assert parse_dice("1d20+3") == (1, 20, 3)
    assert parse_dice("1d20-2") == (1, 20, -2)


def test_roll_total_in_range():
    result = roll("d20")
    assert len(result.rolls) == 1
    assert 1 <= result.total <= 20


def test_roll_with_modifier():
    result = roll("1d6+2")
    assert result.modifier == 2
    assert result.total == sum(result.rolls) + 2


def test_invalid_notation():
    with pytest.raises(ValueError):
        roll("invalid")
