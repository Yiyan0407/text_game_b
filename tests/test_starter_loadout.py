from game.character_creation import build_character, roll_ability_scores
from game.models import Character
from game.starter_loadout import (
    StarterEquipmentEntry,
    StarterInventoryEntry,
    StarterLoadout,
    sync_starter_loadout,
)


def test_sync_starter_loadout_adds_skills_inventory_and_equipment():
    character = Character(name="测试")
    loadout = StarterLoadout(
        skills=["潜行（短距离隐蔽）"],
        inventory=[
            StarterInventoryEntry(
                item="旧背包",
                kind="durable",
                description="常年外出用的帆布包",
            ),
            StarterInventoryEntry(
                item="短刀",
                kind="durable",
                description="磨损的防身短刃",
            ),
        ],
        equipment=[StarterEquipmentEntry(item="短刀", slot="hand")],
    )
    events = sync_starter_loadout(character, loadout)
    assert character.skill_names() == ["潜行"]
    assert {item.name for item in character.inventory} == {"旧背包", "短刀"}
    assert character.is_item_equipped("短刀")
    assert any("初始技能" in event for event in events)
    assert any("初始物品" in event for event in events)


def test_build_character_applies_starter_loadout():
    rolled = roll_ability_scores()
    loadout = StarterLoadout(
        skills=["观察（留意细节）"],
        inventory=[
            StarterInventoryEntry(
                item="记事本",
                kind="document",
                description="随身记录线索",
            )
        ],
    )
    character = build_character("测试", "背景", rolled, starter_loadout=loadout)
    assert character.skill_names() == ["观察"]
    assert character.find_inventory_item("记事本") is not None


def test_starter_loadout_generator_parse():
    from game.starter_loadout import parse_starter_loadout_dict

    loadout = parse_starter_loadout_dict(
        {
            "skills": [{"name": "拾荒", "description": "辨认可用残骸"}],
            "inventory": [
                {
                    "item": "水壶",
                    "quantity": 1,
                    "unit": "个",
                    "kind": "durable",
                    "description": "金属水壶，背景持有",
                },
                {
                    "item": "过滤片",
                    "quantity": 3,
                    "unit": "片",
                    "kind": "consumable",
                    "description": "简易净水耗材",
                },
            ],
            "equipment": [{"item": "水壶", "slot": "hand"}],
        }
    )
    assert loadout.skills == ["拾荒（辨认可用残骸）"]
    assert len(loadout.inventory) == 2
    assert loadout.inventory[0].item == "水壶"
    assert loadout.equipment[0].item == "水壶"


def test_starter_loadout_generator_skips_equipment_not_in_inventory():
    from game.starter_loadout import parse_starter_loadout_dict

    loadout = parse_starter_loadout_dict(
        {
            "skills": [],
            "inventory": [
                {"item": "绳索", "kind": "durable", "description": "背景持有"}
            ],
            "equipment": [{"item": "不存在的长剑", "slot": "hand"}],
        }
    )
    assert loadout.equipment == []
