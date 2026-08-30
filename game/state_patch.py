"""世界状态补丁：解析 StatePatch 并应用到 Character / GameState。"""

import logging
from typing import Literal

from pydantic import ValidationError

from config.settings import get_settings
from game.combat import end_combat
from game.inventory import (
    MECHANICAL_COMBAT_LOOT_DESCRIPTION,
    MECHANICAL_PICKUP_DESCRIPTION,
    MECHANICAL_PURCHASE_DESCRIPTION,
    item_name_from_ref,
)
from game.post_kp_mechanics import combat_pickup_reserved
from game.models import Character, GameState
from game.results import (
    ActionRouteResult,
    BackgroundProcessPatch,
    DeadlinePatch,
    EquipmentPatch,
    InventoryPatch,
    MemoryFactPatch,
    NpcPatch,
    QuestPatch,
    RerollPatch,
    ScenePatch,
    SkillPatch,
    StatePatch,
    TimePatch,
)
from game.text_match import fuzzy_match_name
from game.narrative_time import apply_turn_time_from_patch

logger = logging.getLogger(__name__)


def apply_inventory_change(
    character: Character,
    patch: InventoryPatch,
    *,
    delivered_items: frozenset[str] | None = None,
    added_this_turn: set[str] | None = None,
) -> str:
    """应用单条背包变更，含防重复逻辑。"""
    delivered = delivered_items or frozenset()
    added = added_this_turn if added_this_turn is not None else set()
    cleaned = patch.item.strip()
    if not cleaned:
        return "物品名称不能为空。"
    quantity = max(1, patch.quantity or 1)
    if quantity <= 0:
        return "数量必须大于 0。"
    item_name = item_name_from_ref(cleaned) or cleaned
    unit = patch.unit or "个"
    description = patch.description or ""

    if patch.action == "add":
        if not description.strip():
            return f"跳过添加：{item_name} 缺少物品描述。"
        if delivered and any(
            fuzzy_match_name(item_name, delivered_name) for delivered_name in delivered
        ):
            return f"跳过重复添加：{item_name}（已在交易结算中交付）。"
        if item_name in added:
            existing = character.find_inventory_item(cleaned)
            if existing and description.strip() and not existing.description.strip():
                existing.description = description.strip()
                return f"已补充描述：{existing.format_detail()}"
            return f"跳过重复添加：{item_name}（本轮已入库）。"
        if character.add_inventory_item(
            cleaned,
            quantity=quantity,
            unit=unit,
            description=description,
            kind=patch.kind,
        ):
            added.add(item_name)
            matched = character.find_inventory_item(cleaned)
            label = matched.format_detail() if matched else cleaned
            return f"获得：{label}"
        return "添加失败。"

    ok, message = character.consume_inventory_quantity(
        cleaned,
        quantity,
        unit=unit if unit != "个" else None,
    )
    return message if ok else message


def apply_state_patch(
    patch: StatePatch,
    character: Character,
    game_state: GameState,
    *,
    route: ActionRouteResult | None = None,
    delivered_items: frozenset[str] | None = None,
    mechanical_events: list[str] | None = None,
    user_input: str = "",
    apply_time: bool = True,
    inventory_sync: bool = False,
    recent_history: str = "",
    scene_record_turn: int | None = None,
) -> list[str]:
    """将 StatePatch 应用到游戏状态，返回事件列表。"""
    events: list[str] = []
    mechanical = mechanical_events or []
    added_this_turn: set[str] = set()
    in_combat = game_state.is_in_combat()
    roll_failed = _mechanical_roll_failed(mechanical)
    purchase_settled = route is not None and _purchase_settled_from_route(route, mechanical)

    record_turn = (
        scene_record_turn
        if scene_record_turn is not None
        else game_state.turn_count
    )

    if patch.scene and patch.scene.scene_id.strip() and patch.scene.scene_name.strip():
        if in_combat:
            events.append("跳过场景变更：战斗中无法切换场景。")
        else:
            result = _apply_scene(game_state, patch.scene, record_turn=record_turn)
            if result:
                events.append(result)

    for npc in patch.npcs:
        result = _apply_npc(game_state, npc)
        if result:
            events.append(result)

    for quest in patch.quests:
        result = _apply_quest(game_state, quest)
        if result:
            events.append(result)

    for inv in patch.inventory:
        if inv.action != "add":
            continue
        item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
        if (
            inventory_sync
            and item_name
            and _mechanical_already_settled_item(mechanical, item_name)
        ):
            enriched = _enrich_inventory_from_item_sync(character, inv)
            if enriched:
                events.append(enriched)
            continue
        if _should_block_inventory_add(
            route,
            mechanical,
            inv,
            character,
            in_combat,
            inventory_sync=inventory_sync,
        ):
            events.append(
                _inventory_add_block_reason(
                    route,
                    mechanical,
                    inv,
                    character,
                    in_combat,
                    inventory_sync=inventory_sync,
                )
            )
            continue
        if purchase_settled:
            item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
            if delivered_items and any(
                fuzzy_match_name(item_name, d) for d in delivered_items
            ):
                events.append(f"跳过重复添加：{item_name}（已在交易结算中交付）。")
                continue
        events.append(
            apply_inventory_change(
                character,
                inv,
                delivered_items=delivered_items,
                added_this_turn=added_this_turn,
            )
        )

    for equip in patch.equipment:
        if equip.action != "unequip":
            continue
        result = _apply_equipment(character, equip)
        if result:
            events.append(result)

    unequipped_items = _unequipped_item_names(patch.equipment)

    for inv in patch.inventory:
        if inv.action != "remove":
            continue
        if _should_block_inventory_remove(route, mechanical, inv):
            events.append(
                f"跳过重复移除：{inv.item}（机械层已消耗或扣款）。"
            )
            continue
        if _should_block_inventory_remove_on_unequip(character, inv, unequipped_items):
            events.append(_inventory_remove_block_reason(character, inv, unequipped_items))
            continue
        events.append(
            apply_inventory_change(
                character,
                inv,
                delivered_items=delivered_items,
                added_this_turn=added_this_turn,
            )
        )

    for equip in patch.equipment:
        if equip.action != "equip":
            continue
        result = _apply_equipment(character, equip)
        if result:
            events.append(result)

    for skill in patch.skills:
        if skill.action == "add" and roll_failed:
            events.append(f"跳过技能添加：{skill.skill}（检定未成功）。")
            continue
        if skill.action == "add" and route and route.skill_usage == "learn" and roll_failed:
            events.append(f"跳过技能添加：{skill.skill}（学习未成功）。")
            continue
        result = _apply_skill(character, skill)
        if result:
            events.append(result)

    memory_facts_added = 0
    for fact in patch.memory_facts:
        if memory_facts_added >= 2:
            break
        if isinstance(fact, MemoryFactPatch):
            payload: str | dict = fact.model_dump(exclude_none=True)
            text = fact.text.strip()
        elif isinstance(fact, dict):
            payload = fact
            text = str(fact.get("text") or fact.get("fact") or "").strip()
        else:
            payload = str(fact).strip()
            text = payload
        if text:
            settings = get_settings()
            added = game_state.add_memory_entries([payload], settings.max_memory_facts)
            for item in added:
                events.append(f"已记录关键事实：{item}")
                memory_facts_added += 1

    from game.background_process import register_background_process, resolve_background_processes

    for process_patch in patch.background_processes:
        events.extend(register_background_process(game_state, process_patch))

    if apply_time:
        events.extend(
            apply_turn_time_from_patch(
                game_state,
                patch.time,
                route=route,
                user_input=user_input,
                character=character,
                has_time_field=patch.time is not None,
                mechanical_events=mechanical,
                recent_history=recent_history,
            )
        )
    events.extend(resolve_background_processes(game_state))

    if patch.end_combat and game_state.is_in_combat():
        events.append(end_combat(game_state))

    return [event for event in events if event]


def _apply_scene(
    game_state: GameState,
    scene: ScenePatch,
    *,
    record_turn: int | None = None,
) -> str:
    from game.scene_map import apply_scene_change

    changed = apply_scene_change(
        game_state,
        scene.scene_id,
        scene.scene_name,
        turn_count=record_turn if record_turn is not None else game_state.turn_count,
    )
    if not changed:
        return ""
    return f"场景已更新：{scene.scene_name}（{scene.scene_id}）"


def _apply_npc(game_state: GameState, npc: NpcPatch) -> str:
    name = npc.name.strip()
    if not name:
        return ""
    attitude = npc.attitude if npc.attitude in ("friendly", "neutral", "hostile", "unknown") else "unknown"
    game_state.upsert_npc(name=name, attitude=attitude, notes=npc.notes.strip())
    return f"已记录 NPC：{name}（{attitude}）"


def _apply_quest(game_state: GameState, quest: QuestPatch) -> str:
    quest_id = quest.quest_id.strip()
    title = quest.title.strip()
    if not quest_id:
        return ""
    if not title:
        return ""
    status = quest.status if quest.status in ("active", "completed", "failed") else "active"
    game_state.upsert_quest(
        quest_id=quest_id,
        title=title,
        status=status,
        description=quest.description.strip(),
    )
    return f"任务已更新：[{quest_id}] {title}（{status}）"


def _apply_skill(character: Character, skill: SkillPatch) -> str:
    cleaned = skill.skill.strip()
    if not cleaned:
        return ""
    if skill.action == "add":
        if character.add_skill(cleaned, description=skill.description):
            matched = character.find_skill(cleaned)
            label = matched.format_detail() if matched else cleaned
            return f"习得技能：{label}"
        if character.has_skill(cleaned):
            return f"已拥有技能：{cleaned}"
        return "添加失败。"
    if character.remove_skill(cleaned):
        return f"失去技能：{cleaned}"
    return f"你没有这项技能：{cleaned}"


def _apply_equipment(character: Character, patch: EquipmentPatch) -> str:
    from game.equipment import EquipmentSlot, coerce_equipment_slot, is_valid_equipment_slot

    slot: EquipmentSlot | None = None
    if patch.slot.strip() and is_valid_equipment_slot(patch.slot.strip()):
        slot = coerce_equipment_slot(patch.slot.strip())

    if patch.action == "equip":
        item = patch.item.strip()
        if not item:
            return ""
        ok, message = character.equip_item(item, slot=slot)
        return message if ok else f"跳过装备：{message}"

    ok, message = character.unequip_item(patch.item.strip(), slot=patch.slot.strip())
    return message if ok else ""


def _unequipped_item_names(equipment_patches) -> set[str]:
    names: set[str] = set()
    for patch in equipment_patches:
        if patch.action != "unequip":
            continue
        cleaned = patch.item.strip()
        if cleaned:
            names.add(cleaned)
    return names


def _inventory_remove_quantity(inv: InventoryPatch) -> int:
    return max(1, inv.quantity or 1)


def _should_block_inventory_remove_on_unequip(
    character: Character,
    inv: InventoryPatch,
    unequipped_items: set[str],
) -> bool:
    item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
    if not item_name:
        return False
    target = character.find_inventory_item(inv.item.strip())
    if target is None:
        return False
    remove_qty = _inventory_remove_quantity(inv)
    # 仅移除多余数量（如重复同步导致 qty>1），保留仍装备或应留在背包的那一份
    if remove_qty < target.quantity:
        return False
    if any(fuzzy_match_name(item_name, name) for name in unequipped_items):
        return True
    return character.is_item_equipped(item_name)


def _inventory_remove_block_reason(
    character: Character,
    inv: InventoryPatch,
    unequipped_items: set[str],
) -> str:
    item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
    target = character.find_inventory_item(inv.item.strip())
    remove_qty = _inventory_remove_quantity(inv)
    if target is not None and remove_qty < target.quantity:
        return f"跳过移除：{item_name}（数量不足或未指定部分移除）"
    if any(fuzzy_match_name(item_name, name) for name in unequipped_items):
        return f"跳过移除：{item_name}（卸下后应保留在背包，勿 inventory remove）"
    return f"跳过移除：{item_name}（仍装备中，请先 equipment unequip；卸下后物品回背包）"


def _is_mechanical_inventory_placeholder(description: str) -> bool:
    stripped = description.strip()
    return stripped in {
        MECHANICAL_PICKUP_DESCRIPTION,
        MECHANICAL_PURCHASE_DESCRIPTION,
        MECHANICAL_COMBAT_LOOT_DESCRIPTION,
    }


def _enrich_inventory_from_item_sync(character: Character, inv: InventoryPatch) -> str:
    """机械层已入库时，ItemSync 用叙事 description/kind 覆盖占位信息。"""
    existing = character.find_inventory_item(inv.item)
    if existing is None:
        return ""
    incoming_desc = inv.description.strip()
    updated = False
    if incoming_desc and (
        _is_mechanical_inventory_placeholder(existing.description)
        or not existing.description.strip()
        or len(incoming_desc) > len(existing.description.strip())
    ):
        existing.description = incoming_desc
        updated = True
    if inv.kind in ("consumable", "durable", "document") and not existing.kind:
        existing.kind = inv.kind
        updated = True
    if not updated:
        return ""
    return f"已补充描述：{existing.format_detail()}"


def _mechanical_roll_failed(mechanical_events: list[str]) -> bool:
    for event in mechanical_events:
        if "检定" in event and ("失败" in event or "失败 ✗" in event):
            return True
    return False


def _mechanical_already_settled_item(
    mechanical_events: list[str],
    item_name: str,
) -> bool:
    """机械层本轮已交付/持用/使用该物品。"""
    markers = ("获得：", "装备：", "持用：", "握持：", "收起：", "卸下：", "使用：")
    for event in mechanical_events:
        if not any(marker in event for marker in markers):
            continue
        if fuzzy_match_name(item_name, event):
            return True
    return False


def _mechanical_granted_pickup(
    mechanical_events: list[str],
    item_name: str,
) -> bool:
    """机械层本轮拾取成功（获得：）。"""
    return any(
        "获得：" in event and fuzzy_match_name(item_name, event)
        for event in mechanical_events
    )


def _should_block_inventory_add(
    route: ActionRouteResult | None,
    mechanical_events: list[str],
    inv: InventoryPatch,
    character: Character,
    in_combat: bool,
    *,
    inventory_sync: bool = False,
) -> bool:
    if inv.action != "add":
        return False
    item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
    if not item_name:
        return False

    if _mechanical_already_settled_item(mechanical_events, item_name):
        return True

    if route and route.combat_action == "end_turn":
        return True

    if inventory_sync:
        if (
            route
            and route.item_usage == "pickup"
            and _mechanical_roll_failed(mechanical_events)
            and route.referenced_items
            and any(fuzzy_match_name(item_name, ref) for ref in route.referenced_items)
        ):
            return True
        if (
            in_combat
            and route
            and route.item_usage == "pickup"
            and route.referenced_items
            and any(fuzzy_match_name(item_name, ref) for ref in route.referenced_items)
            and not _mechanical_granted_pickup(mechanical_events, item_name)
            and not combat_pickup_reserved(mechanical_events, item_name)
        ):
            return True
        # ItemSync（KP 叙事后）：NPC 交付/叙事拾取等以 KP 为准
        return False

    if route and route.item_usage == "use" and character.has_inventory_item(item_name):
        if route.referenced_items and any(
            fuzzy_match_name(item_name, ref) for ref in route.referenced_items
        ):
            return True

    return False


def _should_block_inventory_remove(
    route: ActionRouteResult | None,
    mechanical_events: list[str],
    inv: InventoryPatch,
) -> bool:
    if inv.action != "remove":
        return False
    item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
    if not item_name:
        return False
    for event in mechanical_events:
        if not fuzzy_match_name(item_name, event):
            continue
        if any(
            marker in event
            for marker in ("使用：", "背包移除", "背包更新", "支付失败")
        ):
            return True
    if route and route.item_usage == "purchase":
        for payment in route.payment_items:
            if fuzzy_match_name(item_name, payment) and any(
                "背包" in event for event in mechanical_events
            ):
                return True
    return False


def _inventory_add_block_reason(
    route: ActionRouteResult | None,
    mechanical_events: list[str],
    inv: InventoryPatch,
    character: Character,
    in_combat: bool,
    *,
    inventory_sync: bool = False,
) -> str:
    item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
    if _mechanical_already_settled_item(mechanical_events, item_name):
        return f"跳过重复添加：{inv.item}（机械层已结算该物品）。"
    if route and route.item_usage == "use" and character.has_inventory_item(item_name):
        if route.referenced_items and any(
            fuzzy_match_name(item_name, ref) for ref in route.referenced_items
        ):
            return f"跳过重复添加：{inv.item}（装备已有物品，不得重复入库）。"
    if route and route.combat_action == "end_turn":
        return f"跳过重复添加：{inv.item}（结束回合不会获得物品）。"
    if (
        inventory_sync
        and route
        and route.item_usage == "pickup"
        and _mechanical_roll_failed(mechanical_events)
        and route.referenced_items
        and any(fuzzy_match_name(item_name, ref) for ref in route.referenced_items)
    ):
        return f"跳过重复添加：{inv.item}（拾取检定失败，不得入库）。"
    if (
        inventory_sync
        and in_combat
        and route
        and route.item_usage == "pickup"
        and route.referenced_items
        and any(fuzzy_match_name(item_name, ref) for ref in route.referenced_items)
        and not _mechanical_granted_pickup(mechanical_events, item_name)
    ):
        return f"跳过重复添加：{inv.item}（战斗中须先消耗拾取动作且 KP 前已记录）。"
    return f"跳过重复添加：{inv.item}（须与机械层结算一致）。"


def _purchase_settled_from_route(route: ActionRouteResult, mechanical_events: list[str]) -> bool:
    if route.item_usage != "purchase":
        return False
    if any("支付失败" in event for event in mechanical_events):
        return False
    return any("获得：" in event or "背包新增" in event for event in mechanical_events)


def patch_from_dict(data: dict) -> StatePatch:
    """从 JSON dict 构建 StatePatch。"""
    scene_data = data.get("scene")
    scene = None
    if isinstance(scene_data, dict):
        scene = ScenePatch(
            scene_id=str(scene_data.get("scene_id", "")).strip(),
            scene_name=str(scene_data.get("scene_name", "")).strip(),
        )

    npcs = _coerce_npc_list(data.get("npcs"))
    quests = _coerce_quest_list(data.get("quests"))
    inventory = _coerce_inventory_list(data.get("inventory"))
    equipment = _coerce_equipment_list(data.get("equipment"))
    skills = _coerce_skill_list(data.get("skills"))
    memory_facts = _coerce_memory_facts_list(data.get("memory_facts"))
    background_processes = _coerce_background_process_list(data.get("background_processes"))
    end_combat = bool(data.get("end_combat", False))
    map_discovery = bool(data.get("map_discovery", False))
    time = _coerce_time_patch(data.get("time"))
    reroll = _coerce_reroll_patch(data.get("reroll"))

    return StatePatch(
        scene=scene,
        npcs=npcs,
        quests=quests,
        inventory=inventory,
        equipment=equipment,
        skills=skills,
        memory_facts=memory_facts,
        background_processes=background_processes,
        time=time,
        end_combat=end_combat,
        reroll=reroll,
        map_discovery=map_discovery,
    )


def _coerce_reroll_patch(value) -> RerollPatch | None:
    if not isinstance(value, dict):
        return None
    try:
        adjusted_dc = max(0, int(value.get("adjusted_dc", 0) or 0))
    except (TypeError, ValueError):
        adjusted_dc = 0
    patch = RerollPatch(
        grant=bool(value.get("grant", False)),
        overturn_failure=bool(value.get("overturn_failure", False)),
        adjusted_dc=adjusted_dc,
        ability=str(value.get("ability", "")).strip(),
        action_hint=str(value.get("action_hint", "")).strip(),
        reason=str(value.get("reason", "")).strip(),
    )
    if not patch.grant and not patch.overturn_failure:
        return None
    return patch


def sanitize_kp_meta_patch(patch: StatePatch) -> StatePatch:
    """KP 出戏沟通：允许 inventory/equipment 修正（由 KP meta AI 裁定）；禁止推进时间或登记新时限。"""
    if patch.time is None:
        return patch
    patch.time.advance_minutes = 0
    patch.time.advance_reason = ""
    patch.time.time_label = ""
    patch.time.deadlines = []
    return patch


def _coerce_memory_facts_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        items: list = []
        for item in value:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    items.append(cleaned)
                continue
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("fact") or "").strip()
                if not text:
                    continue
                topic = str(item.get("topic") or item.get("category") or "").strip()
                tags = item.get("tags") or []
                items.append(
                    MemoryFactPatch(
                        text=text,
                        topic=topic,
                        tags=tags if isinstance(tags, list) else [],
                    )
                )
        return items
    return []


def _coerce_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _coerce_npc_list(value) -> list[NpcPatch]:
    if not isinstance(value, list):
        return []
    npcs: list[NpcPatch] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        attitude = str(item.get("attitude", "unknown")).strip().lower()
        if attitude not in ("friendly", "neutral", "hostile", "unknown"):
            attitude = "unknown"
        npcs.append(
            NpcPatch(
                name=str(item.get("name", "")).strip(),
                attitude=attitude,  # type: ignore[arg-type]
                notes=str(item.get("notes", "")).strip(),
            )
        )
    return [npc for npc in npcs if npc.name]


def _coerce_quest_list(value) -> list[QuestPatch]:
    if not isinstance(value, list):
        return []
    quests: list[QuestPatch] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "active")).strip().lower()
        if status not in ("active", "completed", "failed"):
            status = "active"
        quests.append(
            QuestPatch(
                quest_id=str(item.get("quest_id", "")).strip(),
                title=str(item.get("title", "")).strip(),
                status=status,  # type: ignore[arg-type]
                description=str(item.get("description", "")).strip(),
            )
        )
    return [q for q in quests if q.quest_id]


def _coerce_inventory_list(value) -> list[InventoryPatch]:
    if not isinstance(value, list):
        return []
    items: list[InventoryPatch] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "add")).strip().lower()
        if action not in ("add", "remove"):
            action = "add"
        qty = item.get("quantity", 1)
        try:
            quantity = max(1, int(qty))
        except (TypeError, ValueError):
            quantity = 1
        kind_raw = str(item.get("kind", "")).strip().lower()
        kind = (
            kind_raw
            if kind_raw in ("consumable", "durable", "document")
            else None
        )
        try:
            items.append(
                InventoryPatch(
                    action=action,  # type: ignore[arg-type]
                    item=str(item.get("item", "")).strip(),
                    quantity=quantity,
                    unit=str(item.get("unit", "个")).strip() or "个",
                    description=str(item.get("description", "")).strip(),
                    kind=kind,  # type: ignore[arg-type]
                )
            )
        except ValidationError as exc:
            item_label = str(item.get("item", "")).strip() or "（未命名）"
            logger.warning(
                "跳过无效 inventory 条目 %s：%s",
                item_label,
                exc.errors()[0].get("msg", exc),
            )
    return [inv for inv in items if inv.item]


def _coerce_equipment_list(value) -> list[EquipmentPatch]:
    if not isinstance(value, list):
        return []
    entries: list[EquipmentPatch] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "equip")).strip().lower()
        if action not in ("equip", "unequip"):
            action = "equip"
        entries.append(
            EquipmentPatch(
                action=action,  # type: ignore[arg-type]
                item=str(item.get("item", "")).strip(),
                slot=str(item.get("slot", "")).strip(),
            )
        )
    return [
        entry
        for entry in entries
        if entry.action == "unequip" or entry.item or entry.slot
    ]


def _coerce_skill_list(value) -> list[SkillPatch]:
    if not isinstance(value, list):
        return []
    skills: list[SkillPatch] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "add")).strip().lower()
        if action not in ("add", "remove"):
            action = "add"
        skills.append(
            SkillPatch(
                action=action,  # type: ignore[arg-type]
                skill=str(item.get("skill", "")).strip(),
                description=str(item.get("description", "")).strip(),
            )
        )
    return [s for s in skills if s.skill]


def _coerce_background_process_list(value) -> list[BackgroundProcessPatch]:
    if not isinstance(value, list):
        return []
    processes: list[BackgroundProcessPatch] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            duration = max(1, int(item.get("duration_minutes", 1) or 1))
        except (TypeError, ValueError):
            duration = 1
        processes.append(
            BackgroundProcessPatch(
                id=str(item.get("id", "")).strip(),
                label=str(item.get("label", "")).strip(),
                duration_minutes=duration,
                result_fact=str(item.get("result_fact", "")).strip(),
                blocks_actions=str(item.get("blocks_actions", "")).strip(),
            )
        )
    return [process for process in processes if process.label]


def _coerce_deadline_list(value) -> list[DeadlinePatch]:
    if not isinstance(value, list):
        return []
    deadlines: list[DeadlinePatch] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "pending")).strip().lower()
        if status not in ("pending", "cancelled"):
            status = "pending"
        due_at_raw = item.get("due_at_minutes")
        due_at = None
        if due_at_raw is not None and due_at_raw != "":
            try:
                due_at = max(0, int(due_at_raw))
            except (TypeError, ValueError):
                due_at = None
        try:
            due_in = max(0, int(item.get("due_in_minutes", 0) or 0))
        except (TypeError, ValueError):
            due_in = 0
        try:
            hp_loss = max(0, int(item.get("hp_loss", 0) or 0))
        except (TypeError, ValueError):
            hp_loss = 0
        deadlines.append(
            DeadlinePatch(
                id=str(item.get("id", "")).strip(),
                label=str(item.get("label", "")).strip(),
                due_in_minutes=due_in,
                due_at_minutes=due_at,
                consequence=str(item.get("consequence", "")).strip(),
                status=status,  # type: ignore[arg-type]
                fail_quest_ids=_coerce_str_list(item.get("fail_quest_ids")),
                hp_loss=hp_loss,
            )
        )
    return [d for d in deadlines if d.label]


def _coerce_time_patch(value) -> TimePatch | None:
    if not isinstance(value, dict):
        return None
    try:
        advance = max(0, int(value.get("advance_minutes", 0) or 0))
    except (TypeError, ValueError):
        advance = 0
    return TimePatch(
        time_label=str(value.get("time_label", "")).strip(),
        advance_minutes=advance,
        advance_reason=str(value.get("advance_reason", "")).strip(),
        deadlines=_coerce_deadline_list(value.get("deadlines")),
        cancel_deadline_ids=_coerce_str_list(value.get("cancel_deadline_ids")),
        enforce_deadline_ids=_coerce_str_list(value.get("enforce_deadline_ids")),
    )
