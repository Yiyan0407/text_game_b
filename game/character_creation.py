from dataclasses import dataclass

from game.dice import roll_4d6_drop_lowest
from game.models import ABILITY_ORDER, Character, compute_max_hp


@dataclass(frozen=True)
class AbilityRollDetail:
    key: str
    field: str
    label: str
    score: int
    rolls: tuple[int, ...]
    dropped: int


@dataclass(frozen=True)
class RolledAbilities:
    details: tuple[AbilityRollDetail, ...]

    def to_character_fields(self) -> dict[str, int]:
        return {detail.field: detail.score for detail in self.details}

    def total_score(self) -> int:
        return sum(detail.score for detail in self.details)


def roll_ability_scores() -> RolledAbilities:
    """六项属性各掷 4d6 去掉最低一颗，经典 D&D 创角方式。"""
    details: list[AbilityRollDetail] = []
    for key, field, label in ABILITY_ORDER:
        score, rolls, dropped = roll_4d6_drop_lowest()
        details.append(
            AbilityRollDetail(
                key=key,
                field=field,
                label=label,
                score=score,
                rolls=rolls,
                dropped=dropped,
            )
        )
    return RolledAbilities(details=tuple(details))


def build_character(name: str, background: str, rolled: RolledAbilities) -> Character:
    fields = rolled.to_character_fields()
    max_hp = compute_max_hp(fields["constitution"])
    return Character(
        name=name,
        background=background,
        hp=max_hp,
        max_hp=max_hp,
        **fields,
    )
