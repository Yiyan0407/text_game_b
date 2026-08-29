"""探索/战斗中共用的物品使用机械结算。"""

from __future__ import annotations

from game.effect_use import item_has_resolved_use, resolve_item_use
from game.models import Character, GameState


def resolve_use_item(
    character: Character,
    item_refs: list[str],
    *,
    game_state: GameState | None = None,
    attack_target: str = "",
) -> list[str]:
    if not item_refs:
        return ["未指定要使用的物品。"]

    item_ref = item_refs[0].strip()
    if not item_ref:
        return ["未指定要使用的物品。"]

    if not character.has_inventory_item(item_ref):
        return [f"背包中没有：{item_ref}"]

    target = character.find_inventory_item(item_ref)
    if target is None:
        return [f"背包中没有：{item_ref}"]

    if target.kind == "document":
        return [
            f"查阅：{target.format_detail()}",
            "具体内容由 KP 叙事描述；物品仍保留在背包。",
        ]

    use_events = resolve_item_use(
        character,
        target,
        item_ref,
        game_state=game_state,
        attack_target=attack_target,
    )
    if use_events is not None:
        return use_events

    has_attack = bool(target.effects and target.effects.attack_damage.strip())
    if target.kind == "durable" or has_attack:
        if has_attack and character.is_item_equipped(target.name):
            return [f"{target.name} 已装备并就绪，可直接攻击。"]
        if target.kind == "durable" and character.is_item_in_hand(target.name):
            ok, message = character.unequip_item(target.name)
            return [message if ok else f"卸下失败：{message}"]
        ok, message = character.equip_item(target.name, slot="hand")
        if not ok:
            return [message]
        return [message, "具体效果由 KP 叙事描述。"]

    ok, consume_msg = character.consume_inventory_quantity(item_ref, 1)
    if not ok:
        return [f"使用失败：{consume_msg}"]

    return [f"使用：{target.name}（{consume_msg}）"]
