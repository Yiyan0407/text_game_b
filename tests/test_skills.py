from game.models import Character
from game.opening_brief import OpeningBrief
from game.skills import (
    infer_starter_skills,
    merge_starter_skill_candidates,
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
    assert character.skills == ["航海", "观测天气"]


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
