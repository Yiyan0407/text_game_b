"""物品使用（use_item）效果结算。"""

from __future__ import annotations

from game.combat_modifiers import apply_use_tag
from game.dice import roll, roll_damage
from game.effect_resolver import apply_damage_to_enemy
from game.inventory import InventoryItem
from game.models import Character, CombatEnemy, GameState

_USE_TAG_HINTS: dict[str, str] = {
    "snare": "束缚或迟滞效果（叙事配合）",
    "trap": "陷阱已布置（叙事配合；触发伤害另由场景裁定）",
    "utility": "战术效果（叙事配合）",
}


def heal_notation_for_item(item: InventoryItem) -> str:
    effects = item.effects
    if effects and effects.heals_on_use():
        return effects.heal_dice
    return ""


def item_has_resolved_use(item: InventoryItem) -> bool:
    effects = item.effects
    if effects and effects.forged:
        return effects.has_use_effect()
    return False


def resolve_item_use(
    character: Character,
    item: InventoryItem,
    item_ref: str,
    *,
    game_state: GameState | None = None,
    attack_target: str = "",
) -> list[str] | None:
    """结算 use_item；无使用通道效果时返回 None。"""
    effects = item.effects
    if not effects or not effects.forged or not effects.has_use_effect():
        return None

    heal_notation = heal_notation_for_item(item)
    use_damage = effects.use_damage
    use_tag = effects.use_tag
    use_auto_hit = effects.use_auto_hit
    use_aoe = effects.use_aoe

    consumes = effects.consumes_when_used()
    if consumes:
        ok, consume_msg = character.consume_inventory_quantity(item_ref, 1)
        if not ok:
            return [f"使用失败：{consume_msg}"]
        events = [f"使用：{item.name}（{consume_msg}）"]
    else:
        events = [f"使用：{item.name}"]

    if heal_notation:
        events.extend(_apply_heal_lines(character, heal_notation))

    if use_damage:
        events.extend(
            _apply_use_damage_lines(
                character,
                item,
                use_damage,
                game_state=game_state,
                attack_target=attack_target,
                auto_hit=use_auto_hit,
                aoe=use_aoe,
            )
        )

    if use_tag and game_state and game_state.combat:
        tag_events = apply_use_tag(game_state.combat, use_tag)
        if tag_events:
            events.extend(tag_events)
        elif use_tag.lower() not in ("smoke", "flash"):
            hint = _USE_TAG_HINTS.get(use_tag.lower(), use_tag)
            events.append(f"📦 {item.name}：{hint}")

    return events


def _apply_heal_lines(character: Character, heal_notation: str) -> list[str]:
    heal_roll = roll_damage(heal_notation)
    healed = heal_roll.total
    before = character.hp
    max_hp = character.effective_max_hp()
    character.hp = min(max_hp, character.hp + healed)
    actual = character.hp - before
    return [
        f"🎲 治疗 {heal_roll.describe()} = {healed} HP，"
        f"恢复 {actual} 点生命（{character.hp}/{max_hp}）"
    ]


def _apply_use_damage_lines(
    character: Character,
    item: InventoryItem,
    damage_notation: str,
    *,
    game_state: GameState | None,
    attack_target: str,
    auto_hit: bool,
    aoe: bool,
) -> list[str]:
    combat = game_state.combat if game_state else None
    if not combat or not combat.active:
        return [f"{item.name} 需对敌人使用，当前无战斗目标。"]

    targets = _resolve_damage_targets(combat, attack_target, aoe=aoe)
    if not targets:
        return [f"使用 {item.name} 需指定 attack_target。"]

    lines: list[str] = []
    damage_roll = roll_damage(damage_notation)
    raw_damage = max(0, damage_roll.total)

    for enemy in targets:
        lines.extend(
            _damage_enemy_with_use_item(
                character,
                item,
                enemy,
                damage_notation,
                raw_damage,
                damage_roll.describe(),
                auto_hit=auto_hit,
            )
        )
    return lines


def _resolve_damage_targets(
    combat,
    attack_target: str,
    *,
    aoe: bool,
) -> list[CombatEnemy]:
    living = combat.living_enemies()
    if not living:
        return []
    if aoe:
        return living
    target_name = attack_target.strip()
    if not target_name and len(living) == 1:
        return living
    enemy = combat.get_enemy(target_name) if target_name else None
    if enemy is None or enemy.hp <= 0:
        return []
    return [enemy]


def _damage_enemy_with_use_item(
    character: Character,
    item: InventoryItem,
    enemy: CombatEnemy,
    damage_notation: str,
    raw_damage: int,
    roll_desc: str,
    *,
    auto_hit: bool,
) -> list[str]:
    if auto_hit:
        hit_line = f"对 {enemy.name} 自动生效"
    else:
        attr_mod = character.modifier("dex")
        attack_roll = roll(f"1d20{attr_mod:+d}")
        hit = attack_roll.total >= enemy.ac
        if not hit:
            return [
                f"投掷 {item.name}@{enemy.name}：1d20[{attack_roll.rolls[0]}]{attr_mod:+d}="
                f"{attack_roll.total} vs AC {enemy.ac} → 未命中"
            ]
        hit_line = (
            f"投掷命中 {enemy.name}：1d20[{attack_roll.rolls[0]}]{attr_mod:+d}="
            f"{attack_roll.total} vs AC {enemy.ac}"
        )

    result = apply_damage_to_enemy(enemy, raw_damage)
    lines = [f"💥 {hit_line} · {item.name} {roll_desc} = {raw_damage} 点"]
    if result.effective_sp > 0:
        lines.append(
            f"（SP {result.effective_sp} 阻挡，实际 HP -{result.hp_loss}，"
            f"{enemy.name} 剩余 {enemy.hp}/{enemy.max_hp}）"
        )
    else:
        lines.append(f"（{enemy.name} HP -{result.hp_loss}，剩余 {enemy.hp}/{enemy.max_hp}）")
    return lines
