"""战斗中的武器/profile 解析。"""

from __future__ import annotations

from dataclasses import dataclass

from game.item_kinds import _WEAPON_KEYWORDS
from game.models import Character
from game.results import ActionRouteResult
from game.text_match import fuzzy_match_name

_FIREARM_KEYWORDS = ("枪", "手枪", "步枪", "霰弹", "冲锋枪", "格洛克", "glock", "pistol", "gun")
_MELEE_KEYWORDS = ("剑", "刀", "匕首", "棍", "斧", "锤", "弓", "弩", "短剑", "长剑")
_MARTIAL_KEYWORDS = (
    "武术",
    "格斗",
    "拳",
    "掌",
    "腿",
    "脚",
    "奔雷",
    "搏击",
    "跆拳道",
    "拳击",
    "散打",
    "功夫",
    "拳法",
    "掌法",
    "腿法",
)
_ADVANCED_MARTIAL_KEYWORDS = ("奔雷", "铁砂", "八极", "咏春", "太极", "洪拳", "大师")
_DEX_MARTIAL_KEYWORDS = ("身法", "敏捷", "轻功", "闪击", "快拳")


@dataclass(frozen=True)
class WeaponProfile:
    label: str
    use_dex: bool
    damage_notation: str
    attack_bonus: int = 0


def _is_firearm(name: str) -> bool:
    lowered = name.lower()
    return any(keyword in name or keyword in lowered for keyword in _FIREARM_KEYWORDS)


def _is_melee_weapon(name: str) -> bool:
    return any(keyword in name for keyword in _MELEE_KEYWORDS)


def _is_martial_skill(skill_name: str) -> bool:
    return any(keyword in skill_name for keyword in _MARTIAL_KEYWORDS)


def _martial_damage_notation(skill_name: str) -> str:
    if any(keyword in skill_name for keyword in _ADVANCED_MARTIAL_KEYWORDS):
        return "1d8"
    return "1d6"


def _martial_uses_dex(skill_name: str) -> bool:
    return any(keyword in skill_name for keyword in _DEX_MARTIAL_KEYWORDS)


def _resolve_martial_skill(
    character: Character,
    route: ActionRouteResult | None,
) -> str | None:
    candidates: list[str] = []
    if route is not None:
        if route.skill_usage == "use":
            candidates.extend(route.referenced_skills)
        combined = f"{route.action_intent} {route.scope_stop}"
        for skill_name in character.skill_names():
            if skill_name and skill_name in combined:
                candidates.append(skill_name)
    candidates.extend(character.skill_names())

    seen: set[str] = set()
    for ref in candidates:
        skill = character.find_skill(ref)
        if skill is None:
            continue
        name = skill.name.strip()
        if not name or name in seen:
            continue
        if _is_martial_skill(name):
            seen.add(name)
            return name
    return None


def _unarmed_profile(
    character: Character,
    route: ActionRouteResult | None,
) -> WeaponProfile:
    martial_skill = _resolve_martial_skill(character, route)
    if martial_skill is None:
        return WeaponProfile(label="徒手", use_dex=False, damage_notation="1d4")
    return WeaponProfile(
        label=f"徒手（{martial_skill}）",
        use_dex=_martial_uses_dex(martial_skill),
        damage_notation=_martial_damage_notation(martial_skill),
        attack_bonus=2,
    )


def _weapon_from_item_name(name: str) -> WeaponProfile | None:
    cleaned = name.strip()
    if not cleaned or not any(keyword in cleaned for keyword in _WEAPON_KEYWORDS):
        return None
    if _is_firearm(cleaned):
        return WeaponProfile(label=cleaned, use_dex=True, damage_notation="1d10")
    if _is_melee_weapon(cleaned):
        return WeaponProfile(label=cleaned, use_dex=False, damage_notation="1d8")
    return WeaponProfile(label=cleaned, use_dex=False, damage_notation="1d6")


def _active_weapon(character: Character) -> WeaponProfile | None:
    for entry in character.active_gear:
        if entry.slot != "weapon":
            continue
        profile = _weapon_from_item_name(entry.item_name)
        if profile is not None:
            return profile
    return None


def _referenced_weapon(character: Character, route: ActionRouteResult | None) -> WeaponProfile | None:
    if route is None:
        return None
    for ref in route.referenced_items:
        if not character.has_inventory_item(ref):
            continue
        profile = _weapon_from_item_name(ref)
        if profile is not None:
            return profile
    return None


def resolve_weapon_profile(
    character: Character,
    route: ActionRouteResult | None = None,
) -> WeaponProfile:
    for resolver in (
        lambda: _referenced_weapon(character, route),
        lambda: _active_weapon(character),
        lambda: _inventory_weapon(character),
    ):
        profile = resolver()
        if profile is not None:
            return _apply_skill_bonus(character, profile)
    return _unarmed_profile(character, route)


def _inventory_weapon(character: Character) -> WeaponProfile | None:
    for item in character.inventory:
        profile = _weapon_from_item_name(item.name)
        if profile is not None:
            return profile
    return None


def _apply_skill_bonus(character: Character, profile: WeaponProfile) -> WeaponProfile:
    bonus = 0
    for skill_name in character.skill_names():
        if fuzzy_match_name(profile.label, skill_name) or fuzzy_match_name(skill_name, profile.label):
            bonus = 2
            break
        if profile.use_dex and any(keyword in skill_name for keyword in ("射击", "枪械", "弓术")):
            bonus = 2
            break
        if not profile.use_dex and _is_martial_skill(skill_name):
            bonus = 2
            break
    if bonus == 0:
        return profile
    return WeaponProfile(
        label=profile.label,
        use_dex=profile.use_dex,
        damage_notation=profile.damage_notation,
        attack_bonus=bonus,
    )


def ensure_weapon_ready(character: Character, profile: WeaponProfile) -> None:
    if profile.label == "徒手" or profile.label.startswith("徒手（"):
        return
    item = character.find_inventory_item(profile.label)
    if item is None:
        return
    character.set_active_gear(item)
