"""测试用 StatForge effects 夹具。"""

from game.inventory import InventoryItem
from game.skills import Skill


def forged_weapon(name: str, damage: str = "1d10", *, use_dex: bool = True) -> InventoryItem:
    return InventoryItem(
        name=name,
        quantity=1,
        unit="把",
        kind="durable",
        effects={
            "attack_damage": damage,
            "use_dex": use_dex,
            "forged": True,
        },
    )


def forged_heal_item(name: str = "治疗药水", heal: str = "2d4+2") -> InventoryItem:
    return InventoryItem(
        name=name,
        quantity=1,
        effects={"heal_dice": heal, "forged": True},
    )


def forged_martial_skill(name: str = "奔雷掌", damage: str = "1d8") -> Skill:
    return Skill(
        name=name,
        description="",
        effects={"attack_damage": damage, "attack_bonus": 2, "forged": True},
    )


def forged_aoe_grenade(name: str = "手雷", damage: str = "2d6") -> InventoryItem:
    return InventoryItem(
        name=name,
        quantity=1,
        effects={
            "use_damage": damage,
            "use_aoe": True,
            "use_auto_hit": True,
            "forged": True,
        },
    )


def forged_smoke(name: str = "烟雾弹") -> InventoryItem:
    return InventoryItem(
        name=name,
        quantity=1,
        effects={"use_tag": "smoke", "forged": True},
    )
