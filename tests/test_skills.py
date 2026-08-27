from game.models import Character
from game.opening_brief import OpeningBrief
from game.skills import (
    Skill,
    infer_starter_skills,
    merge_starter_skill_candidates,
    parse_skill_text,
    sync_starter_skills,
)


def test_infer_starter_skills_from_hacker_background():
    skills = infer_starter_skills("地下有名的黑客，擅长渗透")
    assert "计算机渗透" in skills


def test_infer_starter_skills_from_fisherman_background():
    skills = infer_starter_skills("灰港老渔民，常年出海")
    assert "航海" in skills


def test_sync_starter_skills_skips_duplicates():
    character = Character(name="测试", skills=["航海"])
    added = sync_starter_skills(character, ["航海", "观测天气"])
    assert added == ["观测天气"]
    assert character.skill_names() == ["航海", "观测天气"]


def test_merge_starter_skill_candidates_respects_limit():
    merged = merge_starter_skill_candidates(
        ["急救", "潜行"],
        ["急救", "开锁", "追踪"],
        limit=2,
    )
    assert merged == ["急救", "潜行"]


def test_opening_brief_includes_starter_skills_hint():
    brief = OpeningBrief(starter_skills=["计算机渗透", "网络侦查"])
    text = brief.format_for_kp()
    assert "背景隐含技能" in text
    assert "计算机渗透" in text


def test_skill_format_detail():
    skill = Skill(name="潜行", description="在阴影中移动不易被察觉。")
    assert skill.format_detail() == "潜行 — 在阴影中移动不易被察觉。"


def test_parse_skill_text_splits_parenthetical_description():
    skill = parse_skill_text("计算机渗透（漏洞捕捉与利用）")
    assert skill.name == "计算机渗透"
    assert skill.description == "漏洞捕捉与利用"


def test_parse_skill_text_explicit_description_overrides_embedded():
    skill = parse_skill_text("潜行（旧说明）", description="新说明")
    assert skill.name == "潜行"
    assert skill.description == "新说明"


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
    assert character.skills[1].name == "电子设备改装与维护"


def test_merge_starter_skill_candidates_dedups_by_skill_name():
    merged = merge_starter_skill_candidates(
        ["计算机渗透（说明A）"],
        ["计算机渗透"],
        limit=3,
    )
    assert merged == ["计算机渗透（说明A）"]
