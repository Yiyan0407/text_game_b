"""世界状态补丁：解析 StatePatch 并应用到 Character / GameState。"""

from typing import Literal

from config.settings import get_settings
from game.combat import end_combat
from game.inventory import item_name_from_ref
from game.models import Character, GameState
from game.results import (
    ActionRouteResult,
    DeadlinePatch,
    EquipmentPatch,
    InventoryPatch,
    NpcPatch,
    QuestPatch,
    ScenePatch,
    SkillPatch,
    StatePatch,
    TimePatch,
)
from game.text_match import fuzzy_match_name
from game.narrative_time import apply_turn_time_from_patch


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
        if delivered and any(
            fuzzy_match_name(item_name, delivered_name) for delivered_name in delivered
        ):
            return f"跳过重复添加：{item_name}（已在交易结算中交付）。"
        if item_name in added:
            existing = character.find_inventory_item(cleaned)
            if existing and description.strip() and not existing.description.strip():
                existing.description = description.strip()
                return f"已补充描述：{existing.format_detail()}"
            if quantity == 1 and (not unit or unit == "个"):
                return f"跳过重复添加：{item_name}（本轮已入库）。"
        if character.add_inventory_item(
            cleaned,
            quantity=quantity,
            unit=unit,
            description=description,
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
) -> list[str]:
    """将 StatePatch 应用到游戏状态，返回事件列表。"""
    events: list[str] = []
    mechanical = mechanical_events or []
    added_this_turn: set[str] = set()
    in_combat = game_state.is_in_combat()
    roll_failed = _mechanical_roll_failed(mechanical)
    purchase_settled = route is not None and _purchase_settled_from_route(route, mechanical)

    if patch.scene and patch.scene.scene_id.strip() and patch.scene.scene_name.strip():
        if in_combat:
            events.append("跳过场景变更：战斗中无法切换场景。")
        else:
            events.append(_apply_scene(game_state, patch.scene))

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
        if _should_block_inventory_add(
            route, mechanical, inv, character, in_combat
        ):
            events.append(
                _inventory_add_block_reason(route, mechanical, inv, character, in_combat)
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

    for equip in patch.equipment:
        if equip.action != "equip":
            continue
        result = _apply_equipment(character, equip)
        if result:
            events.append(result)

    events.extend(
        _auto_equip_added_items(
            character,
            patch,
            added_this_turn,
        )
    )

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

    for fact in patch.memory_facts:
        cleaned = fact.strip()
        if cleaned:
            settings = get_settings()
            game_state.add_memory_facts([cleaned], settings.max_memory_facts)
            events.append(f"已记录关键事实：{cleaned}")

    events.extend(
        apply_turn_time_from_patch(
            game_state,
            patch.time,
            route=route,
            user_input=user_input,
            character=character,
            has_time_field=patch.time is not None,
        )
    )

    if patch.end_combat and game_state.is_in_combat():
        events.append(end_combat(game_state))

    return [event for event in events if event]


def _apply_scene(game_state: GameState, scene: ScenePatch) -> str:
    game_state.scene_id = scene.scene_id.strip()
    game_state.current_scene = scene.scene_name.strip()
    game_state.scene_image_url = ""
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
    if not quest_id or not title:
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


_INVENTORY_EQUIP_DESCRIPTION_MARKERS = (
    "已植入",
    "已装备",
    "已穿戴",
    "已挂载",
    "已装配",
    "安装完成",
    "植入完成",
)


def _inventory_add_implies_equip(inv: InventoryPatch) -> bool:
    description = inv.description.strip()
    if not description:
        return False
    return any(marker in description for marker in _INVENTORY_EQUIP_DESCRIPTION_MARKERS)


def _explicit_equip_item_names(patch: StatePatch) -> set[str]:
    names: set[str] = set()
    for entry in patch.equipment:
        if entry.action != "equip":
            continue
        cleaned = entry.item.strip()
        if cleaned:
            names.add(cleaned)
    return names


def _auto_equip_added_items(
    character: Character,
    patch: StatePatch,
    added_this_turn: set[str],
) -> list[str]:
    """State Agent 在 inventory description 中标明已装备/已植入时的兜底 equip。"""
    if not added_this_turn:
        return []

    events: list[str] = []
    explicit = _explicit_equip_item_names(patch)

    for inv in patch.inventory:
        if inv.action != "add":
            continue
        if not _inventory_add_implies_equip(inv):
            continue
        item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
        if not item_name:
            continue
        if not any(fuzzy_match_name(item_name, added) for added in added_this_turn):
            continue
        if any(fuzzy_match_name(item_name, name) for name in explicit):
            continue
        if character.is_item_equipped(item_name):
            continue
        ok, message = character.equip_item(item_name)
        if ok:
            events.append(message)
    return events


def _unequipped_item_names(equipment_patches) -> set[str]:
    names: set[str] = set()
    for patch in equipment_patches:
        if patch.action != "unequip":
            continue
        cleaned = patch.item.strip()
        if cleaned:
            names.add(cleaned)
    return names


def _should_block_inventory_remove_on_unequip(
    character: Character,
    inv: InventoryPatch,
    unequipped_items: set[str],
) -> bool:
    item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
    if not item_name:
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
    if any(fuzzy_match_name(item_name, name) for name in unequipped_items):
        return f"跳过移除：{item_name}（卸下后应保留在背包，勿 inventory remove）"
    return f"跳过移除：{item_name}（仍装备中，请先 equipment unequip；卸下后物品回背包）"


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
) -> bool:
    if inv.action != "add":
        return False
    item_name = item_name_from_ref(inv.item.strip()) or inv.item.strip()
    if not item_name:
        return False

    if _mechanical_already_settled_item(mechanical_events, item_name):
        return True

    if route and route.item_usage == "use" and character.has_inventory_item(item_name):
        if route.referenced_items and any(
            fuzzy_match_name(item_name, ref) for ref in route.referenced_items
        ):
            return True

    if route and route.item_usage == "pickup" and not _mechanical_granted_pickup(
        mechanical_events, item_name
    ):
        return True

    if in_combat and not _mechanical_granted_pickup(mechanical_events, item_name):
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
    if route and route.item_usage == "pickup":
        return f"跳过重复添加：{inv.item}（拾取未成功，不得凭空入库）。"
    if in_combat:
        return f"跳过重复添加：{inv.item}（战斗中须机械层拾取成功才可入库）。"
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
    memory_facts = _coerce_str_list(data.get("memory_facts"))
    end_combat = bool(data.get("end_combat", False))
    time = _coerce_time_patch(data.get("time"))

    return StatePatch(
        scene=scene,
        npcs=npcs,
        quests=quests,
        inventory=inventory,
        equipment=equipment,
        skills=skills,
        memory_facts=memory_facts,
        time=time,
        end_combat=end_combat,
    )


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
    return [q for q in quests if q.quest_id and q.title]


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
        items.append(
            InventoryPatch(
                action=action,  # type: ignore[arg-type]
                item=str(item.get("item", "")).strip(),
                quantity=quantity,
                unit=str(item.get("unit", "个")).strip() or "个",
                description=str(item.get("description", "")).strip(),
            )
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
        deadlines=_coerce_deadline_list(value.get("deadlines")),
        cancel_deadline_ids=_coerce_str_list(value.get("cancel_deadline_ids")),
    )
