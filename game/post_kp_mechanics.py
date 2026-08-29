"""KP 叙事后的探索模式机械结算（购买、用物）。"""

from __future__ import annotations

from game.inventory import (
    MECHANICAL_COMBAT_LOOT_DESCRIPTION,
    MECHANICAL_PURCHASE_DESCRIPTION,
    item_name_from_ref,
)
from game.item_use import resolve_use_item
from game.models import Character, GameState
from game.results import ActionRouteResult
from game.text_match import fuzzy_match_name


def execute_purchase(route: ActionRouteResult, character: Character) -> list[str]:
    events: list[str] = []
    quantity = max(1, route.payment_quantity or 1)

    if not route.payment_items:
        events.append("支付失败：未指定支付物品。")
        return events

    for payment in route.payment_items:
        target = character.find_inventory_item(payment)
        if target is None:
            events.append(f"支付失败：背包中没有：{payment}")
            return events
        if quantity > target.quantity:
            events.append(f"支付失败：背包中 {target.display()} 数量不足。")
            return events

    for payment in route.payment_items:
        ok, message = character.consume_inventory_quantity(payment, quantity)
        if ok:
            events.append(message)
        else:
            events.append(f"支付失败：{message}")
            return events

    for goods in route.referenced_items:
        if character.add_inventory_item(
            goods, description=MECHANICAL_PURCHASE_DESCRIPTION
        ):
            matched = character.find_inventory_item(goods)
            label = matched.format_detail() if matched else goods
            events.append(f"获得：{label}")
    return events


def purchase_settled(route: ActionRouteResult | None, mechanical_events: list[str]) -> bool:
    if route is None or route.item_usage != "purchase":
        return False
    if any("支付失败" in event for event in mechanical_events):
        return False
    return any("获得：" in event or "背包新增" in event for event in mechanical_events)


def delivered_item_names(
    route: ActionRouteResult | None,
    mechanical_events: list[str],
) -> frozenset[str]:
    if not purchase_settled(route, mechanical_events):
        return frozenset()
    return frozenset(
        item_name_from_ref(item)
        for item in route.referenced_items
        if item.strip()
    )


def combat_pickup_reserved(mechanical_events: list[str], item_name: str) -> bool:
    for event in mechanical_events:
        if "免费物件互动" not in event or "拾取" not in event:
            continue
        if fuzzy_match_name(item_name, event):
            return True
    return False


def _combat_use_reserved(mechanical_events: list[str], item_ref: str) -> bool:
    if not item_ref.strip():
        return False
    for event in mechanical_events:
        if "使用" not in event:
            continue
        if not any(
            marker in event for marker in ("免费物件互动", "附加动作", "主要动作")
        ):
            continue
        if fuzzy_match_name(item_ref, event):
            return True
    return False


def _settle_combat_pickup(
    route: ActionRouteResult,
    character: Character,
    pre_kp_events: list[str],
) -> list[str]:
    events: list[str] = []
    for item in route.referenced_items:
        if not combat_pickup_reserved(pre_kp_events, item):
            continue
        if character.add_inventory_item(
            item, description=MECHANICAL_COMBAT_LOOT_DESCRIPTION
        ):
            matched = character.find_inventory_item(item)
            label = matched.format_detail() if matched else item
            events.append(f"获得：{label}")
    return events


def _settle_combat_use(
    route: ActionRouteResult,
    character: Character,
    game_state: GameState,
    pre_kp_events: list[str],
) -> list[str]:
    if not route.referenced_items:
        return []
    item_ref = route.referenced_items[0]
    if not _combat_use_reserved(pre_kp_events, item_ref):
        return []
    return resolve_use_item(
        character,
        route.referenced_items,
        game_state=game_state,
        attack_target=route.attack_target,
    )


def resolve_post_kp_mechanics(
    route: ActionRouteResult,
    character: Character,
    game_state: GameState,
    pre_kp_events: list[str] | None = None,
) -> list[str]:
    """KP 叙事后结算：探索购买/用物；战斗拾取/用物（须 KP 前已扣动作额度）。"""
    pre = list(pre_kp_events or [])
    if game_state.is_in_combat():
        if route.item_usage == "pickup":
            return _settle_combat_pickup(route, character, pre)
        if route.item_usage == "use":
            return _settle_combat_use(route, character, game_state, pre)
        return []
    if route.item_usage == "purchase":
        return execute_purchase(route, character)
    if route.item_usage == "use":
        return resolve_use_item(character, route.referenced_items)
    return []
