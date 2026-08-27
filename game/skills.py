from __future__ import annotations

import re

from game.models import Character

# (背景关键词, 技能列表) —— 保守推断，最多取前几条规则
_STARTER_SKILL_RULES: tuple[tuple[tuple[str, ...], list[str]], ...] = (
    (("黑客", "hacker", "渗透测试", "程序员", "工程师", "运维", "网络安全"), ["计算机渗透", "网络侦查"]),
    (("记者", "编辑", "撰稿人", "狗仔"), ["采访", "观察"]),
    (("渔民", "水手", "船员", "船长", "航海"), ["航海", "观测天气"]),
    (("医生", "护士", "医学生", "药剂"), ["急救", "辨识草药"]),
    (("盗贼", "窃贼", "扒手", "刺客"), ["潜行", "开锁"]),
    (("剑士", "剑客", "武士", "战士", "佣兵"), ["基础剑术"]),
    (("猎人", "猎户", "护林"), ["追踪", "观察"]),
    (("商人", "掌柜", "销售", "ceo", "总裁", "经理"), ["交涉"]),
    (("学者", "研究员", "教授", "图书"), ["调查", "文献检索"]),
    (("修士", "道士", "方士", "炼丹"), ["基础吐纳"]),
    (("剑修", "蜀山", "修仙", "修士"), ["基础剑术", "基础吐纳"]),
)

_WORLD_SKILL_RULES: dict[str, list[tuple[tuple[str, ...], list[str]]]] = {
    "xianxia": (
        (("剑", "剑修", "蜀山"), ["基础剑术"]),
        (("丹", "药", "医"), ["辨识草药"]),
    ),
    "fantasy": (
        (("法师", "术士", "巫师"), ["辨识魔法"]),
        (("游侠", "弓箭"), ["追踪"]),
    ),
}


def infer_starter_skills(background: str, *, world_id: str = "", limit: int = 3) -> list[str]:
    text = background.strip()
    if not text:
        return []
    normalized = re.sub(r"\s+", "", text.lower())
    found: list[str] = []
    seen: set[str] = set()

    def _add_skills(skills: list[str]) -> None:
        for skill in skills:
            key = skill.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            found.append(key)
            if len(found) >= limit:
                return

    for keywords, skills in _STARTER_SKILL_RULES:
        if any(k.lower() in normalized or k in text for k in keywords):
            _add_skills(skills)
            if len(found) >= limit:
                return found

    for keywords, skills in _WORLD_SKILL_RULES.get(world_id, ()):
        if any(k.lower() in normalized or k in text for k in keywords):
            _add_skills(skills)
            if len(found) >= limit:
                return found

    return found


def sync_starter_skills(character: Character, skills: list[str]) -> list[str]:
    added: list[str] = []
    for skill in skills:
        if character.add_skill(skill.strip()):
            added.append(skill.strip())
    return added


def merge_starter_skill_candidates(
    *sources: list[str] | None,
    limit: int = 3,
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for source in sources:
        if not source:
            continue
        for skill in source:
            cleaned = skill.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            merged.append(cleaned)
            if len(merged) >= limit:
                return merged
    return merged
