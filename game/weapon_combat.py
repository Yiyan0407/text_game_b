"""战斗中的武器/profile 解析（仅读 StatForge effects，无关键词兜底）。"""

from __future__ import annotations

from dataclasses import dataclass

from game.equipment import EquipmentSlot
from game.models import Character
from game.results import ActionRouteResult
from game.skills import Skill
from game.text_match import fuzzy_match_name

_EQUIPMENT_WEAPON_SLOTS: tuple[EquipmentSlot, ...] = ("hand", "body", "accessory")


@dataclass(frozen=True)
class WeaponProfile:
    label: str
    use_dex: bool
    damage_notation: str
    attack_bonus: int = 0


def _resolve_active_skill(
    character: Character,
    route: ActionRouteResult | None,
    *,
    user_input: str = "",
) -> Skill | None:
    candidates: list[str] = []
    if route is not None:
        if route.skill_usage == "use":
            candidates.extend(route.referenced_skills)
        for skill_name in character.skill_names():
            if skill_name and user_input and skill_name in user_input:
                candidates.append(skill_name)
        candidates.extend(route.referenced_skills)

    seen: set[str] = set()
    for ref in candidates:
        skill = character.find_skill(ref)
        if skill is None:
            continue
        name = skill.name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if skill.effects and skill.effects.attack_damage.strip():
            return skill
    return None


def _profile_from_skill(skill: Skill) -> WeaponProfile:
    effects = skill.effects
    assert effects is not None and effects.attack_damage.strip()
    bonus = effects.attack_bonus or 2
    return WeaponProfile(
        label=f"徒手（{skill.name}）",
        use_dex=effects.use_dex,
        damage_notation=effects.attack_damage.strip(),
        attack_bonus=bonus,
    )


def _unarmed_profile(
    character: Character,
    route: ActionRouteResult | None,
    *,
    user_input: str = "",
) -> WeaponProfile:
    skill = _resolve_active_skill(character, route, user_input=user_input)
    if skill is not None:
        return _profile_from_skill(skill)
    return WeaponProfile(label="徒手", use_dex=False, damage_notation="1d4")


def _profile_from_item(character: Character, item_name: str) -> WeaponProfile | None:
    item = character.find_inventory_item(item_name)
    if item is None or not item.effects:
        return None
    if item.effects.attack_damage.strip():
        effects = item.effects
        return WeaponProfile(
            label=item.name,
            use_dex=effects.use_dex,
            damage_notation=effects.attack_damage.strip(),
            attack_bonus=effects.attack_bonus,
        )
    return None


def _equipped_weapon(
    character: Character,
    route: ActionRouteResult | None = None,
) -> WeaponProfile | None:
    """任意装备槽中已穿戴且带 attack_damage 的武器均可直接用于攻击。"""
    character.prune_equipment()
    if route is not None:
        for ref in route.referenced_items:
            if not character.is_item_equipped(ref):
                continue
            profile = _profile_from_item(character, ref)
            if profile is not None:
                return profile

    seen: set[str] = set()
    for slot in _EQUIPMENT_WEAPON_SLOTS:
        for entry in character.equipment:
            if entry.slot != slot or entry.item_name in seen:
                continue
            profile = _profile_from_item(character, entry.item_name)
            if profile is not None:
                seen.add(entry.item_name)
                return profile
    return None


def _referenced_weapon(character: Character, route: ActionRouteResult | None) -> WeaponProfile | None:
    if route is None:
        return None
    for ref in route.referenced_items:
        if not character.has_inventory_item(ref):
            continue
        profile = _profile_from_item(character, ref)
        if profile is not None:
            return profile
    return None


def resolve_weapon_profile(
    character: Character,
    route: ActionRouteResult | None = None,
    *,
    user_input: str = "",
) -> WeaponProfile:
    for resolver in (
        lambda: _referenced_weapon(character, route),
        lambda: _equipped_weapon(character, route),
        lambda: _inventory_weapon(character),
    ):
        profile = resolver()
        if profile is not None:
            return _apply_skill_bonus(character, profile)
    return _unarmed_profile(character, route, user_input=user_input)


def _inventory_weapon(character: Character) -> WeaponProfile | None:
    for item in character.inventory:
        if character.is_item_equipped(item.name):
            continue
        profile = _profile_from_item(character, item.name)
        if profile is not None:
            return profile
    return None


def _apply_skill_bonus(character: Character, profile: WeaponProfile) -> WeaponProfile:
    if profile.attack_bonus > 0:
        return profile
    for skill in character.skills:
        skill_name = skill.name
        if fuzzy_match_name(profile.label, skill_name) or fuzzy_match_name(skill_name, profile.label):
            return WeaponProfile(
                label=profile.label,
                use_dex=profile.use_dex,
                damage_notation=profile.damage_notation,
                attack_bonus=2,
            )
    return profile


def ensure_weapon_ready(character: Character, profile: WeaponProfile) -> None:
    if profile.label == "徒手" or profile.label.startswith("徒手（"):
        return
    item = character.find_inventory_item(profile.label)
    if item is None:
        return
    if character.is_item_equipped(item.name):
        return
    if not character.is_item_in_hand(item.name):
        character.equip_item(item.name, slot="hand")


def _is_unarmed_profile(profile: WeaponProfile) -> bool:
    return profile.label == "徒手" or profile.label.startswith("徒手（")


def weapon_is_active(character: Character, profile: WeaponProfile) -> bool:
    if _is_unarmed_profile(profile):
        return True
    item = character.find_inventory_item(profile.label)
    if item is None:
        return False
    return character.is_item_equipped(item.name)


def weapon_needs_draw(character: Character, profile: WeaponProfile) -> bool:
    if _is_unarmed_profile(profile):
        return False
    if weapon_is_active(character, profile):
        return False
    return character.has_inventory_item(profile.label)


def draw_weapon_for_attack(
    character: Character,
    combat,
    profile: WeaponProfile,
) -> tuple[bool, str]:
    """尝试将武器装备到手持槽。返回 (成功与否, 说明)。"""
    if not weapon_needs_draw(character, profile):
        ensure_weapon_ready(character, profile)
        return True, ""

    item = character.find_inventory_item(profile.label)
    if item is None:
        return False, f"你没有携带 {profile.label}，无法用于攻击。"

    if combat is None or not combat.has_free_interact():
        return False, (
            f"本回合免费物件互动已用尽，无法将 {profile.label} 拿到手上。"
            "可先拾取并装备到手持，或下回合再行动。"
        )

    combat.spend_free_interact()
    ok, message = character.equip_item(item.name, slot="hand")
    if not ok:
        return False, message
    return True, f"装备到手持：{item.name}"
