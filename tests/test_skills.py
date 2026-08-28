from game.models import Character
from game.skills import (
    Skill,
    coerce_skill_list,
    parse_skill_text,
    sync_starter_skills,
)


def test_coerce_skill_list_from_dicts():
    skills = coerce_skill_list(
        [
            {"name": "计算机渗透", "description": "漏洞分析"},
            "采访（套话）",
        ]
    )
    assert skills == ["计算机渗透（漏洞分析）", "采访（套话）"]


def test_sync_starter_skills_skips_duplicates():
    character = Character(name="测试", skills=["航海"])
    added = sync_starter_skills(character, ["航海", "观测天气"])
    assert added == ["观测天气"]
    assert character.skill_names() == ["航海", "观测天气"]


def test_skill_format_detail():
    skill = Skill(name="潜行", description="在阴影中移动不易被察觉。")
    assert skill.format_detail() == "潜行 — 在阴影中移动不易被察觉。"


def test_parse_skill_text_splits_parenthetical_description():
    skill = parse_skill_text("计算机渗透（漏洞捕捉与利用）")
    assert skill.name == "计算机渗透"
    assert skill.description == "漏洞捕捉与利用"


def test_normalize_skills_splits_legacy_embedded_description():
    character = Character(name="测试", skills=["基础潜行（生存本能）"])
    assert character.skills[0].name == "基础潜行"
    assert character.skills[0].description == "生存本能"


def test_sync_starter_skills_splits_parenthetical_description():
    character = Character(name="测试")
    sync_starter_skills(
        character,
        ["计算机渗透（漏洞捕捉与利用）", "电子设备改装与维护（制作骇入装置）"],
    )
    assert character.skills[0].name == "计算机渗透"
    assert character.skills[0].description == "漏洞捕捉与利用"


def test_starter_skills_generator_parse():
    from chain.starter_skills_generator import StarterSkillsGenerator

    payload = '{"skills": [{"name": "航海", "description": "近海航行"}, "观察"]}'
    skills = StarterSkillsGenerator._parse_response(payload)
    assert skills == ["航海（近海航行）", "观察"]


def test_starter_skills_generator_prompt_variables():
    from chain.starter_skills_generator import StarterSkillsGenerator

    generator = StarterSkillsGenerator()
    formatted = generator.prompt.format_messages(
        world_rules="规则",
        world_id="fantasy",
        background="灰港老渔民",
    )
    assert formatted
    assert '"name"' in formatted[0].content
