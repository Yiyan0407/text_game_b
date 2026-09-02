from game.appearance import CharacterAppearance, merge_appearance, parse_appearance_dict
from game.models import Character
from game.profile import CharacterCard
from chain.character_portrait import build_portrait_prompt


def test_parse_appearance_dict():
    data = {
        "gender": "女",
        "age": "青年",
        "ancestry": "人类",
        "hair": "黑色短发",
    }
    appearance = parse_appearance_dict(data)
    assert appearance.gender == "女"
    assert appearance.age == "青年"
    assert appearance.format_for_prompt().startswith("性别：女")


def test_portrait_prompt_includes_appearance():
    card = CharacterCard.from_character(Character(name="艾拉", background="雾港调查员"))
    card.appearance = CharacterAppearance(
        gender="女",
        age="约 30 岁",
        ancestry="人类",
        hair="深色卷发",
    )
    text = build_portrait_prompt(card, world_id="coc")
    assert "性别：女" in text
    assert "约 30 岁" in text
    assert "严格遵循上述性别" in text


def test_merge_appearance_keeps_manual_gender_age():
    manual = CharacterAppearance(gender="女", age="青年")
    inferred = CharacterAppearance(gender="男", age="中年", ancestry="精灵", hair="银发")
    merged = merge_appearance(manual, inferred)
    assert merged.gender == "女"
    assert merged.age == "青年"
    assert merged.ancestry == "精灵"
    assert merged.hair == "银发"


def test_appearance_empty_when_unknown():
    appearance = CharacterAppearance()
    assert appearance.is_empty()
    assert appearance.format_for_prompt() == ""
