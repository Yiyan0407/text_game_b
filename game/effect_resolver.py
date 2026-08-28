"""SP 阻挡力与伤害结算。"""

from __future__ import annotations

from dataclasses import dataclass

from game.effects import EntityEffects
from game.models import Character, CombatEnemy


@dataclass
class DamageResult:
    raw_damage: int
    effective_sp: int
    hp_loss: int
    sp_before: int = 0
    sp_after: int = 0
    sp_source: str = ""
    armor_broken: bool = False
    fully_blocked: bool = False

    def format_events(self) -> list[str]:
        if self.fully_blocked and self.effective_sp > 0:
            return [
                f"🛡️ SP{self.effective_sp} 完全挡住 {self.raw_damage} 点伤害，护甲未磨损。"
            ]
        if self.hp_loss <= 0:
            return [f"受到 0 点伤害（原始 {self.raw_damage}）。"]

        lines = [
            f"💥 受到 {self.hp_loss} 点伤害（原始 {self.raw_damage}，SP {self.effective_sp} 阻挡）。"
        ]
        if self.sp_source and self.sp_before > 0:
            if self.armor_broken:
                lines.append(
                    f"🛡️ {self.sp_source} 损毁（SP {self.sp_before}→0）。"
                )
            elif self.sp_after != self.sp_before:
                lines.append(
                    f"🛡️ {self.sp_source} 磨损（SP {self.sp_before}→{self.sp_after}）。"
                )
        return lines


def get_item_effects(character: Character, item_name: str) -> EntityEffects | None:
    item = character.find_inventory_item(item_name)
    if item is None or item.effects is None:
        return None
    return item.effects


def get_effective_sp(character: Character) -> tuple[int, str]:
    """有效 SP = 已装备物品中 SP 最高值（不叠加）。"""
    character.prune_equipment()
    best_sp = 0
    best_name = ""
    for entry in character.equipment:
        effects = get_item_effects(character, entry.item_name)
        if effects is None or effects.sp <= 0:
            continue
        if effects.sp > best_sp:
            best_sp = effects.sp
            best_name = entry.item_name
    return best_sp, best_name


def sum_equipped_ac_bonus(character: Character) -> int:
    character.prune_equipment()
    total = 0
    for entry in character.equipment:
        effects = get_item_effects(character, entry.item_name)
        if effects and effects.ac_bonus:
            total += effects.ac_bonus
    return total


def sum_equipped_max_hp_bonus(character: Character) -> int:
    character.prune_equipment()
    total = 0
    for entry in character.equipment:
        effects = get_item_effects(character, entry.item_name)
        if effects and effects.max_hp_bonus:
            total += effects.max_hp_bonus
    return total


def _degrade_sp_source(character: Character, item_name: str) -> tuple[int, int, bool]:
    item = character.find_inventory_item(item_name)
    if item is None or item.effects is None or item.effects.sp <= 0:
        return 0, 0, False

    before = item.effects.sp
    item.effects.sp = max(0, before - 1)
    after = item.effects.sp
    broken = False
    if after <= 0:
        broken = True
        if "已损毁" not in item.description:
            suffix = "（已损毁）"
            item.description = f"{item.description}{suffix}" if item.description else "已损毁"
        character.unequip_item(item_name)
    return before, after, broken


def apply_incoming_damage(character: Character, raw_damage: int) -> DamageResult:
    effective_sp, source = get_effective_sp(character)
    hp_loss = max(0, raw_damage - effective_sp)

    if hp_loss <= 0:
        return DamageResult(
            raw_damage=raw_damage,
            effective_sp=effective_sp,
            hp_loss=0,
            sp_before=effective_sp,
            sp_after=effective_sp,
            sp_source=source,
            fully_blocked=raw_damage > 0 and effective_sp > 0,
        )

    character.hp = max(0, character.hp - hp_loss)
    sp_before, sp_after, broken = 0, 0, False
    if source:
        sp_before, sp_after, broken = _degrade_sp_source(character, source)

    return DamageResult(
        raw_damage=raw_damage,
        effective_sp=effective_sp,
        hp_loss=hp_loss,
        sp_before=sp_before,
        sp_after=sp_after,
        sp_source=source,
        armor_broken=broken,
    )


def apply_damage_to_enemy(enemy: CombatEnemy, raw_damage: int) -> DamageResult:
    """敌人 SP 仅减伤，不磨损（MVP）。"""
    effective_sp = max(0, enemy.sp)
    hp_loss = max(0, raw_damage - effective_sp)
    if hp_loss > 0:
        enemy.hp = max(0, enemy.hp - hp_loss)

    return DamageResult(
        raw_damage=raw_damage,
        effective_sp=effective_sp,
        hp_loss=hp_loss,
        sp_before=effective_sp,
        sp_after=effective_sp,
        fully_blocked=raw_damage > 0 and hp_loss == 0 and effective_sp > 0,
    )
