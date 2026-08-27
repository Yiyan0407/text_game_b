from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

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


_SKILL_DESC_RE = re.compile(r"^(.+?)（(.+?)）$")


def parse_skill_text(text: str, description: str = "") -> Skill:
    """解析「技能名（说明）」或纯技能名；显式 description 优先于括号内说明。"""
    raw = text.strip()
    explicit = description.strip()
    if not raw:
        raise ValueError("技能名称不能为空")

    match = _SKILL_DESC_RE.match(raw)
    if match:
        name = match.group(1).strip()
        embedded = match.group(2).strip()
        if not name:
            raise ValueError("技能名称不能为空")
        return Skill(name=name, description=explicit or embedded)

    return Skill(name=raw, description=explicit)


def split_skill_description(skill: Skill) -> Skill:
    if skill.description.strip():
        return skill
    try:
        return parse_skill_text(skill.name)
    except ValueError:
        return skill


class Skill(BaseModel):
    name: str
    description: str = ""

    @field_validator("name", "description")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    def format_detail(self) -> str:
        if self.description:
            return f"{self.name} — {self.description}"
        return self.name


def normalize_skills_list(value) -> list[Skill]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("skills must be a list")
    skills: list[Skill] = []
    for entry in value:
        if isinstance(entry, Skill):
            skills.append(split_skill_description(entry))
        elif isinstance(entry, str):
            cleaned = entry.strip()
            if cleaned:
                skills.append(parse_skill_text(cleaned))
        elif isinstance(entry, dict):
            skills.append(split_skill_description(Skill.model_validate(entry)))
        else:
            raise TypeError(f"unsupported skill entry: {entry!r}")
    return skills


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


def sync_starter_skills(character, skills: list[str]) -> list[str]:
    from game.models import Character

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
            if not cleaned:
                continue
            key = parse_skill_text(cleaned).name
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
            if len(merged) >= limit:
                return merged
    return merged
