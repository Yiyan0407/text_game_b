"""SP 阻挡力与 effects 结算测试。"""

from unittest.mock import patch

from game.effect_resolver import (
    apply_damage_to_enemy,
    apply_incoming_damage,
    get_effective_sp,
    sum_equipped_ac_bonus,
)
from game.effect_validate import validate_effects
from game.effects import EntityEffects
from game.models import Character, CombatEnemy
from game.stat_forge import ForgeTarget, collect_forge_targets, mark_entity_skipped


def _character_with_armor(name: str, sp: int, *, slot: str = "body") -> Character:
    character = Character(name="测试")
    character.add_inventory_item(name, description="测试护甲")
    item = character.find_inventory_item(name)
    assert item is not None
    item.effects = EntityEffects(sp=sp, sp_max=sp)
    character.equip_item(name, slot=slot)
    return character


def test_sp8_takes_12_damage():
    character = _character_with_armor("防弹衣", 8)
    character.hp = 20
    result = apply_incoming_damage(character, 12)
    assert result.hp_loss == 4
    assert character.hp == 16
    assert character.find_inventory_item("防弹衣").effects.sp == 7


def test_sp8_blocks_5_damage_no_wear():
    character = _character_with_armor("防弹衣", 8)
    character.hp = 20
    result = apply_incoming_damage(character, 5)
    assert result.hp_loss == 0
    assert result.fully_blocked is True
    assert character.hp == 20
    assert character.find_inventory_item("防弹衣").effects.sp == 8


def test_sp1_breaks_on_heavy_hit():
    character = _character_with_armor("薄甲", 1)
    character.hp = 20
    result = apply_incoming_damage(character, 10)
    assert result.hp_loss == 9
    assert result.armor_broken is True
    assert character.hp == 11
    item = character.find_inventory_item("薄甲")
    assert item.effects.sp == 0
    assert "已损毁" in item.description
    assert not any(entry.item_name == "薄甲" for entry in character.equipment)


def test_effective_sp_takes_max_not_sum():
    character = Character(name="测试")
    for name, sp in (("甲A", 5), ("甲B", 8)):
        character.add_inventory_item(name, description="测试护甲")
        item = character.find_inventory_item(name)
        item.effects = EntityEffects(sp=sp, sp_max=sp)
        character.equip_item(name, slot="body" if name == "甲A" else "accessory")

    effective, source = get_effective_sp(character)
    assert effective == 8
    assert source == "甲B"

    character.hp = 30
    result = apply_incoming_damage(character, 10)
    assert result.hp_loss == 2
    assert character.find_inventory_item("甲B").effects.sp == 7
    assert character.find_inventory_item("甲A").effects.sp == 5


def test_high_damage_vs_low_sp_enemy():
    enemy = CombatEnemy(name="保安", hp=12, max_hp=12, ac=12, sp=2)
    result = apply_damage_to_enemy(enemy, 25)
    assert result.hp_loss == 23
    assert enemy.hp == 0
    assert enemy.sp == 2


def test_enemy_sp_blocks_without_wear():
    enemy = CombatEnemy(name="盾兵", hp=20, max_hp=20, ac=14, sp=8)
    result = apply_damage_to_enemy(enemy, 5)
    assert result.fully_blocked is True
    assert enemy.hp == 20
    assert enemy.sp == 8


def test_validate_effects_clamps_sp():
    effects = validate_effects(
        EntityEffects(sp_max=999, sp=999),
        world_id="modern",
    )
    assert effects.sp_max == 12
    assert effects.sp == 12


def test_validate_effects_heal_dice():
    effects = validate_effects(
        EntityEffects(heal_dice="2d8+4", forged=True),
        world_id="xianxia",
    )
    assert effects.heal_dice == "2d8+4"
    assert effects.format_summary() == "治疗 2d8+4"


def test_sum_equipped_ac_bonus():
    character = Character(name="测试")
    character.add_inventory_item("轻甲", description="轻便护甲")
    item = character.find_inventory_item("轻甲")
    item.effects = EntityEffects(ac_bonus=2)
    character.equip_item("轻甲", slot="body")
    assert sum_equipped_ac_bonus(character) == 2
    assert character.armor_class() == 10 + character.modifier("dex") + 2


def test_roll_compound_damage_notation():
    from game.dice import roll_damage

    with patch("game.dice.random.randint", side_effect=[10, 15]):
        result = roll_damage("1d20+1d20")
    assert result.total == 25
    assert len(result.rolls) == 2


def test_collect_forge_targets_includes_unforged_items_without_keywords():
    character = Character(
        name="测试",
        inventory=["单分子线（1根）", "仓库钥匙（1把）"],
        skills=["潜行（隐蔽移动）"],
    )
    targets = collect_forge_targets(character)
    names = {target.name for target in targets}
    assert "单分子线" in names
    assert "仓库钥匙" in names
    assert "潜行" in names


def test_mark_entity_skipped_sets_forged():
    character = Character(name="测试", inventory=["仓库钥匙"])
    target = ForgeTarget(kind="item", name="仓库钥匙")
    mark_entity_skipped(character, target)
    item = character.find_inventory_item("仓库钥匙")
    assert item.effects is not None
    assert item.effects.forged is True
    assert collect_forge_targets(character) == []


def test_monomolecular_wire_not_in_forge_after_effects_applied():
    character = Character(name="测试", inventory=["单分子线"])
    target = ForgeTarget(kind="item", name="单分子线", description="赛博暗杀用切割线")
    from game.stat_forge import apply_entity_effects

    apply_entity_effects(
        character,
        target,
        EntityEffects(attack_damage="2d10", use_dex=True),
        world_id="cyberpunk",
    )
    item = character.find_inventory_item("单分子线")
    assert item.effects.forged is True
    assert item.effects.attack_damage == "2d10"
    assert collect_forge_targets(character) == []
