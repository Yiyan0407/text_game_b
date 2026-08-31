from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from game.effects import EntityEffects

SkillKind = Literal["active", "passive"]

_SKILL_DESC_RE = re.compile(r"^(.+?)（(.+?)）$")


def normalize_skill_kind(value) -> SkillKind:
    cleaned = str(value or "active").strip().lower()
    if cleaned in ("passive", "被动"):
        return "passive"
    return "active"


def parse_skill_text(
    text: str,
    description: str = "",
    *,
    kind: SkillKind | None = None,
) -> Skill:
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
        return Skill(
            name=name,
            description=explicit or embedded,
            kind=normalize_skill_kind(kind or "active"),
        )

    return Skill(
        name=raw,
        description=explicit,
        kind=normalize_skill_kind(kind or "active"),
    )


def split_skill_description(skill: Skill) -> Skill:
    if skill.description.strip() or skill.effects:
        return skill
    try:
        return parse_skill_text(skill.name)
    except ValueError:
        return skill


class Skill(BaseModel):
    name: str
    description: str = ""
    kind: SkillKind = "active"
    effects: EntityEffects | None = None

    @field_validator("effects", mode="before")
    @classmethod
    def _coerce_effects(cls, value):
        return EntityEffects.coerce(value)

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, value) -> SkillKind:
        return normalize_skill_kind(value)

    @field_validator("name", "description")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @property
    def is_passive(self) -> bool:
        return self.kind == "passive"

    def format_detail(self) -> str:
        tag = "（被动·常驻）" if self.is_passive else ""
        if self.description:
            return f"{self.name}{tag} — {self.description}"
        return f"{self.name}{tag}"


def coerce_skill_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        skills: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                desc = str(item.get("description", "")).strip()
                if name:
                    skills.append(f"{name}（{desc}）" if desc else name)
            else:
                stripped = str(item).strip()
                if stripped:
                    skills.append(stripped)
        return skills
    return []


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


def sync_starter_skills(character, skills: list[str]) -> list[str]:
    added: list[str] = []
    for skill in skills:
        cleaned = skill.strip()
        if cleaned and character.add_skill(cleaned):
            added.append(cleaned)
    return added
