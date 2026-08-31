"""StatForge：为尚未定义 effects 的物品/技能补全数值（由 AI 判断是否战斗相关）。"""

from __future__ import annotations

from dataclasses import dataclass

from game.effect_validate import validate_effects
from game.effects import EntityEffects, is_forge_pending
from game.models import Character


@dataclass(frozen=True)
class ForgeTarget:
    kind: str  # "item" | "skill"
    name: str
    description: str = ""
    skill_kind: str = ""  # active | passive（仅 kind=skill 时）


def collect_forged_references(character: Character) -> list[dict[str, str]]:
    """已裁定实体摘要，供 StatForge 横向比较（避免新入库与旧装备数值倒挂）。"""
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _append(*, kind: str, name: str, description: str, effects: EntityEffects | None, skill_kind: str = "") -> None:
        if not name or not effects or not effects.forged:
            return
        key = (kind, name)
        if key in seen:
            return
        seen.add(key)
        summary = effects.format_summary()
        entry: dict[str, str] = {
            "kind": kind,
            "name": name,
            "description": description.strip() or "（无）",
            "effects": summary or "非战斗/无机械",
        }
        if skill_kind:
            entry["skill_kind"] = skill_kind
        refs.append(entry)

    for item in character.inventory:
        _append(kind="item", name=item.name, description=item.description, effects=item.effects)
    for skill in character.skills:
        _append(
            kind="skill",
            name=skill.name,
            description=skill.description,
            effects=skill.effects,
            skill_kind=skill.kind,
        )
    return refs


def collect_forge_targets(character: Character) -> list[ForgeTarget]:
    """收集所有尚未经 StatForge 裁定的实体（不依赖关键词）。"""
    targets: list[ForgeTarget] = []
    seen: set[tuple[str, str]] = set()
    for item in character.inventory:
        if not is_forge_pending(item.effects):
            continue
        key = ("item", item.name)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            ForgeTarget(kind="item", name=item.name, description=item.description)
        )
    for skill in character.skills:
        if not is_forge_pending(skill.effects):
            continue
        key = ("skill", skill.name)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            ForgeTarget(
                kind="skill",
                name=skill.name,
                description=skill.description,
                skill_kind=skill.kind,
            )
        )
    return targets


def mark_entity_skipped(character: Character, target: ForgeTarget) -> str:
    """AI 判定非战斗实体：写入空 effects 并标记 forged，避免下轮重复询问。"""
    marker = EntityEffects(forged=True)
    if target.kind == "item":
        item = character.find_inventory_item(target.name)
        if item is None:
            return f"StatForge 跳过：未找到物品 {target.name}"
        item.effects = marker
        return f"StatForge·{item.name}：非战斗实体"
    skill = character.find_skill(target.name)
    if skill is None:
        return f"StatForge 跳过：未找到技能 {target.name}"
    skill.effects = marker
    return f"StatForge·{skill.name}：非战斗实体"


def apply_entity_effects(
    character: Character,
    target: ForgeTarget,
    effects: EntityEffects,
    *,
    world_id: str = "",
) -> str:
    effects = effects.model_copy(update={"forged": True})
    effects = validate_effects(effects, world_id=world_id)
    if target.kind == "item":
        item = character.find_inventory_item(target.name)
        if item is None:
            return f"StatForge 跳过：未找到物品 {target.name}"
        item.effects = effects
        summary = effects.format_summary()
        character.clamp_hp_to_effective_max()
        return f"StatForge·{item.name}" + (f"：{summary}" if summary else "")
    skill = character.find_skill(target.name)
    if skill is None:
        return f"StatForge 跳过：未找到技能 {target.name}"
    skill.effects = effects
    summary = effects.format_summary()
    character.clamp_hp_to_effective_max()
    return f"StatForge·{skill.name}" + (f"：{summary}" if summary else "")
