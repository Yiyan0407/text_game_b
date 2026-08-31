import logging

from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.difficulty import ensure_ability_check_dc
from game.models import ABILITY_FIELDS, Character, ChatMessage, GameState
from game.results import ActionRouteResult, AllyDefPatch, EnemyDefPatch
from game.scenario import Scenario
from game.text_match import fuzzy_in_list, resolve_fuzzy_name
from prompts.templates import load_world_prompt


def _payment_available(character: Character, payment: str) -> bool:
    return character.has_inventory_item(payment)


def _payment_sufficient(character: Character, payment: str, quantity: int) -> bool:
    return character.has_sufficient_inventory(payment, quantity)


_DEESCALATION_TALK_MARKERS = (
    "收刀",
    "不再攻击",
    "停止攻击",
    "放下武器",
    "缴械",
    "威慑",
    "投降",
    "举起",
    "退后",
    "住手",
    "别动",
)


def _is_deescalation_talk(user_input: str, route: ActionRouteResult) -> bool:
    if route.combat_action != "talk":
        return False
    text = user_input.strip()
    return any(marker in text for marker in _DEESCALATION_TALK_MARKERS)


def _pickup_covers_attack_weapon(character: Character, route: ActionRouteResult) -> bool:
    if route.item_usage != "pickup" or route.combat_action != "attack":
        return False
    refs = {item.strip() for item in route.referenced_items if item.strip()}
    if not refs:
        return False
    from game.weapon_combat import resolve_weapon_profile

    weapon = resolve_weapon_profile(character, route)
    if weapon.label == "徒手" or weapon.label.startswith("徒手（"):
        return True
    weapon_ref = weapon.item_name or weapon.label.split("（", 1)[0].strip()
    for ref in refs:
        if ref == weapon_ref or ref == weapon.label or ref in weapon.label or weapon.label in ref:
            return True
    return False


def _attack_needs_weapon_draw(
    character: Character,
    route: ActionRouteResult,
    *,
    user_input: str = "",
) -> bool:
    if route.combat_action != "attack":
        return False
    if _pickup_covers_attack_weapon(character, route):
        return False
    from game.weapon_combat import resolve_weapon_profile, weapon_needs_draw

    weapon = resolve_weapon_profile(character, route, user_input=user_input)
    return weapon_needs_draw(character, weapon)


def _free_interact_uses_for_route(
    character: Character,
    route: ActionRouteResult,
    *,
    user_input: str = "",
) -> int:
    uses = 0
    if route.item_usage == "pickup":
        uses += 1
    if route.combat_action == "use_item" and route.action_cost == "free":
        uses += 1
    if _attack_needs_weapon_draw(character, route, user_input=user_input):
        uses += 1
    return uses


def _format_recent_history(history: list[ChatMessage], limit: int = 6) -> str:
    if not history:
        return "（无）"
    recent = history[-limit:]
    lines = []
    for msg in recent:
        role = {"user": "玩家", "assistant": "KP", "system": "系统"}.get(msg.role, msg.role)
        lines.append(f"[{role}] {msg.content}")
    return "\n".join(lines)


INFILTRATION_ACTION_MARKERS = (
    "深入",
    "潜入",
    "潜行",
    "消防通道",
    "溜进",
    "偷溜",
    "避开",
    "翻墙",
    "后门",
    "渗透",
    "非法进入",
    "溜入",
    "摸进",
    "闯入",
    "潜入",
    "撬开",
    "刷卡进入",
    "溜进",
)

STEALTH_ACTION_MARKERS = (
    "隐匿",
    "悄悄",
)

DIALOGUE_ACTION_MARKERS = (
    "询问",
    "问",
    "对话",
    "交谈",
    "聊天",
    "说话",
    "商谈",
    "打听",
    "回答",
    "告诉",
    "解释",
    "说服",
    "请求",
    "求助",
)

RESTRICTED_AREA_SIGNALS = (
    "安保",
    "门禁",
    "机房",
    "非授权",
    "巡逻",
    "数据中心",
    "技术中心",
    "运维中心",
    "星辰",
    "监控",
    "禁止入内",
    "重地",
)


def _looks_like_infiltration_action(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if any(marker in normalized for marker in DIALOGUE_ACTION_MARKERS):
        if not any(marker in normalized for marker in INFILTRATION_ACTION_MARKERS):
            return False
    if any(marker in normalized for marker in INFILTRATION_ACTION_MARKERS):
        return True
    return any(marker in normalized for marker in STEALTH_ACTION_MARKERS)


_WEAPON_ATTACK_MARKERS = (
    "攻击",
    "砍",
    "刺",
    "切开",
    "切割",
    "射击",
    "开枪",
    "挥",
    "击打",
    "打向",
    "招呼",
)
_THROW_MARKERS = (
    "投掷",
    "扔",
    "甩",
    "抛",
    "掷",
    "丢",
)
_APPROACH_MARKERS = (
    "接近",
    "靠近",
    "缩短距离",
    "攻击距离",
    "迎上",
    "冲过去",
    "贴近",
    "拉到",
    "进到",
)


def _input_implies_weapon_attack(user_input: str) -> bool:
    text = user_input.strip()
    return bool(text) and any(marker in text for marker in _WEAPON_ATTACK_MARKERS)


def _input_implies_throw(user_input: str) -> bool:
    text = user_input.strip()
    return bool(text) and any(marker in text for marker in _THROW_MARKERS)


def _input_implies_approach(user_input: str) -> bool:
    text = user_input.strip()
    return bool(text) and any(marker in text for marker in _APPROACH_MARKERS)


def _normalize_combat_attack_route(
    route: ActionRouteResult,
    user_input: str,
) -> None:
    """「接近+使用武器攻击」须走 combat_action=attack，避免误路由为 move / use_item。"""
    if not _input_implies_weapon_attack(user_input):
        return

    if route.combat_action == "move":
        route.combat_action = "attack"
        if not route.attack_target.strip():
            route.attack_target = route.move_target
        route.action_cost = "main"
        route.needs_roll = False
        route.roll_type = "none"

    if route.item_usage == "use" or route.combat_action == "use_item":
        route.combat_action = "attack"
        route.item_usage = "none"
        route.action_cost = "main"
        route.needs_roll = False
        route.roll_type = "none"
    elif route.combat_action == "none":
        route.combat_action = "attack"
        route.action_cost = "main"
        route.needs_roll = False
        route.roll_type = "none"


def _normalize_combat_throw_route(
    route: ActionRouteResult,
    user_input: str,
) -> None:
    """投掷物品须走 use_item + 附加动作，不可误判为快速装备。"""
    if not _input_implies_throw(user_input):
        return
    if route.item_usage not in ("use", "none") and route.combat_action != "use_item":
        return
    route.item_usage = "use"
    route.combat_action = "use_item"
    route.action_cost = "bonus"
    route.needs_roll = False
    route.roll_type = "none"


def _normalize_combat_enemy_refs(
    route: ActionRouteResult,
    combat,
) -> None:
    from game.combat_targets import normalize_combat_enemy_refs

    normalize_combat_enemy_refs(route, combat)


def _normalize_hold_distance_move(
    route: ActionRouteResult,
    combat,
    user_input: str,
) -> None:
    from game.combat_range import DEFAULT_START_DISTANCE_M, attack_range_status
    from game.combat_targets import effective_enemy_distance, normalize_enemy_ref, parse_hold_distance_meters

    hold_m = parse_hold_distance_meters(user_input)
    if hold_m is None:
        return
    if route.combat_action not in ("move", "attack"):
        return

    target = route.move_target.strip() or route.attack_target.strip()
    if not target:
        return

    canonical = normalize_enemy_ref(combat, target)
    if route.move_target.strip() or route.combat_action == "move":
        route.move_target = canonical
    if route.combat_action == "attack" and route.move_meters > 0:
        route.move_target = canonical

    current = effective_enemy_distance(combat, canonical)
    if current > hold_m:
        route.move_toward = True
        route.move_meters = current - hold_m
    elif current < hold_m:
        route.move_toward = False
        route.move_meters = hold_m - current
    elif route.combat_action == "move":
        route.move_meters = 0


def _auto_fill_approach_move_for_attack(
    route: ActionRouteResult,
    character: Character,
    game_state: GameState,
    user_input: str,
) -> None:
    """玩家意图靠近后攻击时，自动补足 move_meters 至射程内（在移动力允许范围内）。"""
    if route.combat_action != "attack" or not route.attack_target.strip():
        return
    combat = game_state.combat
    if not combat:
        return

    from game.combat_range import weapon_range_m
    from game.combat_targets import effective_enemy_distance
    from game.weapon_combat import resolve_weapon_profile

    weapon = resolve_weapon_profile(character, route, user_input=user_input)
    dist = effective_enemy_distance(combat, route.attack_target)
    _, _, hard_max = weapon_range_m(weapon)
    wants_approach = _input_implies_approach(user_input) or route.move_meters > 0
    if dist <= hard_max:
        if route.move_meters > 0:
            route.move_target = route.move_target.strip() or route.attack_target
            route.move_toward = True
        return
    if not wants_approach:
        return

    needed = max(0, dist - hard_max)
    if route.move_meters <= 0:
        route.move_meters = min(needed, combat.movement_remaining_m)
    else:
        route.move_meters = min(
            max(route.move_meters, needed),
            combat.movement_remaining_m,
        )
    route.move_toward = True
    route.move_target = route.move_target.strip() or route.attack_target


def _looks_like_restricted_area(context: str) -> bool:
    return any(signal in context for signal in RESTRICTED_AREA_SIGNALS)


logger = logging.getLogger(__name__)

_PARSE_FAILURE_REASON = "行动裁定解析失败，请重新描述你的行动。"


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in ("true", "1", "yes", "是"):
            return True
        if stripped in ("false", "0", "no", "否"):
            return False
    return default


def _coerce_int(value, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(float(stripped))
        except ValueError:
            return default
    return default


def _coerce_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _route_from_dict(data: dict) -> ActionRouteResult:
    roll_type = data.get("roll_type", "none")
    if roll_type not in ("ability_check", "dice", "none"):
        roll_type = "none"
    item_usage = data.get("item_usage", "none")
    if item_usage not in ("none", "use", "pickup", "observe", "purchase"):
        item_usage = "none"
    skill_usage = data.get("skill_usage", "none")
    if skill_usage not in ("none", "use", "learn"):
        skill_usage = "none"
    mode = data.get("mode", "exploration")
    if mode not in ("exploration", "combat"):
        mode = "exploration"
    combat_action = data.get("combat_action", "none")
    valid_actions = {
        "none", "attack", "flee", "defend", "use_item",
        "interact", "talk", "grapple", "shove", "help", "search",
        "move", "dash", "end_turn",
    }
    if combat_action not in valid_actions:
        combat_action = "none"
    action_cost = data.get("action_cost", "main")
    if action_cost not in ("main", "bonus", "free"):
        action_cost = "main"
    approved = data.get("approved", False)
    if isinstance(approved, str):
        approved = approved.strip().lower() in ("true", "1", "yes", "是", "批准", "通过")
    enemy_defs: list[EnemyDefPatch] = []
    for item in data.get("enemy_defs") or []:
        if isinstance(item, dict):
            try:
                enemy_defs.append(EnemyDefPatch.model_validate(item))
            except (TypeError, ValueError):
                continue
    ally_defs: list[AllyDefPatch] = []
    for item in data.get("ally_defs") or []:
        if isinstance(item, dict):
            try:
                ally_defs.append(AllyDefPatch.model_validate(item))
            except (TypeError, ValueError):
                continue
    return ActionRouteResult(
        approved=bool(approved),
        rejection_reason=str(data.get("rejection_reason", "")).strip(),
        needs_roll=bool(data.get("needs_roll", False)),
        roll_type=roll_type,
        ability=str(data.get("ability", "")).strip().lower(),
        dc=_coerce_int(data.get("dc"), 0),
        dice_notation=str(data.get("dice_notation", "")).strip(),
        referenced_items=_coerce_str_list(data.get("referenced_items")),
        referenced_skills=_coerce_str_list(data.get("referenced_skills")),
        payment_items=_coerce_str_list(data.get("payment_items")),
        payment_quantity=max(1, _coerce_int(data.get("payment_quantity"), 1)),
        item_usage=item_usage,
        skill_usage=skill_usage,
        mode=mode,
        trigger_combat=bool(data.get("trigger_combat", False)),
        enemies_spec=str(data.get("enemies_spec", "")).strip(),
        enemy_defs=enemy_defs,
        ally_defs=ally_defs,
        combat_action=combat_action,
        action_cost=action_cost,
        attack_target=str(data.get("attack_target", "")).strip(),
        move_target=str(data.get("move_target", "")).strip(),
        move_meters=max(0, _coerce_int(data.get("move_meters"), 0)),
        move_toward=_coerce_bool(data.get("move_toward"), True),
        ends_turn=bool(data.get("ends_turn", False)),
        proficiency_bonus=_coerce_bool(data.get("proficiency_bonus"), False),
    )


class ActionRouter:
    def __init__(self):
        self.llm = create_chat_llm(role="action_router", temperature=0.2)
        system_prompt = (PROMPTS_DIR / "action_router.txt").read_text(encoding="utf-8")
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【世界观规则】\n{world_rules}\n\n"
                    "【模组信息】\n{scenario_context}\n\n"
                    "【游戏状态】\n{game_state_context}\n\n"
                    "【玩家角色】\n"
                    "姓名：{character_name}\n"
                    "背景：{character_background}\n"
                    "属性：{character_abilities}\n"
                    "生命：HP {hp}/{max_hp}\n"
                    "背包：{character_inventory}\n"
                    "装备：{character_equipment}\n"
                    "技能：{character_skills}\n\n"
                    "【最近对话】\n{recent_history}\n\n"
                    "【玩家行动】\n{user_input}\n\n"
                    "请输出裁定 JSON：",
                ),
            ]
        )

    def _build_inputs(
        self,
        user_input: str,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
    ) -> dict:
        return {
            "world_rules": load_world_prompt(scenario.world_id),
            "scenario_context": scenario.format_for_prompt(),
            "game_state_context": game_state.format_for_prompt(),
            "character_name": character.name,
            "character_background": character.background,
            "character_abilities": character.format_abilities(),
            "hp": character.hp,
            "max_hp": character.effective_max_hp(),
            "character_inventory": character.format_inventory(),
            "character_equipment": character.format_equipment(),
            "character_skills": character.format_skills(),
            "recent_history": _format_recent_history(history),
            "user_input": user_input.strip(),
        }

    def _finalize_route(
        self,
        text: str,
        user_input: str,
        character: Character,
        game_state: GameState,
        history: list[ChatMessage],
    ) -> ActionRouteResult:
        route = self._parse_route(text)
        route = self.validate(route, character, game_state, user_input=user_input.strip(), history=history)
        return route

    def evaluate(
        self,
        user_input: str,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
    ) -> ActionRouteResult:
        chain = self.prompt | self.llm
        response = chain.invoke(
            self._build_inputs(user_input, character, game_state, scenario, history)
        )
        return self._finalize_route(
            (response.content or "").strip(),
            user_input,
            character,
            game_state,
            history,
        )

    async def aevaluate(
        self,
        user_input: str,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
    ) -> ActionRouteResult:
        chain = self.prompt | self.llm
        response = await chain.ainvoke(
            self._build_inputs(user_input, character, game_state, scenario, history)
        )
        return self._finalize_route(
            (response.content or "").strip(),
            user_input,
            character,
            game_state,
            history,
        )

    @staticmethod
    def _parse_route(text: str) -> ActionRouteResult:
        data = extract_json_dict(text)
        if data is not None:
            try:
                return _route_from_dict(data)
            except (TypeError, ValueError):
                logger.warning("行动路由 JSON 字段异常: %s", text[:500])
        else:
            logger.warning("行动路由 JSON 解析失败: %s", text[:500] or "（空响应）")
        return ActionRouteResult(
            approved=False,
            rejection_reason=_PARSE_FAILURE_REASON,
        )

    @staticmethod
    def validate(
        route: ActionRouteResult,
        character: Character,
        game_state: GameState,
        *,
        user_input: str = "",
        history: list[ChatMessage] | None = None,
    ) -> ActionRouteResult:
        in_combat = game_state.is_in_combat()
        roll_context = _format_recent_history(history or [], limit=6)

        if in_combat:
            _normalize_combat_attack_route(route, user_input)
            _normalize_combat_throw_route(route, user_input)
            route.mode = "combat"
            combat = game_state.combat
            if combat and route.approved:
                _normalize_combat_enemy_refs(route, combat)
                _normalize_hold_distance_move(route, combat, user_input)
            route.trigger_combat = False
            combat = game_state.combat
            if combat and route.approved and not combat.is_player_turn():
                actor = combat.current_actor()
                label = "玩家" if actor == "player" else actor
                route.approved = False
                route.rejection_reason = f"还没轮到你，当前是 {label} 的回合。"
                return route
            if combat and route.approved and route.combat_action not in ("none", "end_turn"):
                if route.combat_action == "move" and not combat.has_movement():
                    route.approved = False
                    route.rejection_reason = "本回合移动力已用尽。"
                    return route
                if (
                    route.combat_action == "talk"
                    and _is_deescalation_talk(user_input, route)
                    and combat.has_bonus_action()
                ):
                    route.action_cost = "bonus"
                elif route.combat_action == "talk" and route.action_cost not in ("main", "bonus"):
                    route.action_cost = "main"
                if route.action_cost == "main" and not combat.has_main_action():
                    route.approved = False
                    route.rejection_reason = (
                        "本回合主要动作已用尽。可使用附加动作，或输入「结束回合」。"
                    )
                    return route
                if route.action_cost == "bonus" and not combat.has_bonus_action():
                    route.approved = False
                    route.rejection_reason = "本回合附加动作已用尽。"
                    return route
            mechanical_actions = {
                "attack", "defend", "flee", "help", "end_turn", "use_item", "move", "dash",
            }
            if route.combat_action in mechanical_actions:
                route.needs_roll = False
                route.roll_type = "none"
        elif route.mode == "combat" and not route.trigger_combat:
            route.mode = "exploration"

        if not route.approved:
            if not route.rejection_reason:
                route.rejection_reason = "该行动无法执行，请重新描述。"
            return route

        if route.trigger_combat:
            if not route.enemies_spec.strip():
                route.approved = False
                route.rejection_reason = "无法确定攻击目标，请明确你要与谁开战。"
                return route
            route.mode = "combat"
            route.needs_roll = False
            route.roll_type = "none"
            # 开战当回合仅结算先攻与先攻更高者行动；玩家战斗指令留到下一轮输入。
            if route.combat_action not in ("none", "end_turn"):
                route.combat_action = "none"
            if route.item_usage in ("pickup", "use", "purchase"):
                route.item_usage = "none"

        if in_combat or route.trigger_combat:
            if route.combat_action == "attack":
                if not route.attack_target.strip():
                    route.approved = False
                    route.rejection_reason = "请明确要攻击的敌人。"
                    return route
                living = game_state.combat.living_enemy_names() if game_state.combat else []
                if route.trigger_combat:
                    living = [
                        part.split(":")[0].strip()
                        for part in route.enemies_spec.split(",")
                        if part.strip()
                    ]
                ally_names = (
                    game_state.combat.living_ally_names() if game_state.combat else []
                )
                if ally_names and fuzzy_in_list(route.attack_target, ally_names):
                    route.approved = False
                    route.rejection_reason = (
                        f"「{route.attack_target}」是友方，不能作为攻击目标。"
                    )
                    return route
                if living and not fuzzy_in_list(route.attack_target, living):
                    route.approved = False
                    route.rejection_reason = (
                        f"找不到存活的敌人「{route.attack_target}」。"
                        f"当前敌人：{'、'.join(living) or '无'}"
                    )
                    return route
                resolved = resolve_fuzzy_name(route.attack_target, living)
                if resolved:
                    route.attack_target = resolved

            if route.combat_action == "move":
                route.action_cost = "free"
                route.needs_roll = False
                route.roll_type = "none"
                if not route.move_target.strip():
                    route.approved = False
                    route.rejection_reason = "移动须指定目标（move_target，通常为敌人名）。"
                    return route
                living = game_state.combat.living_enemy_names() if game_state.combat else []
                if living and not fuzzy_in_list(route.move_target, living):
                    route.approved = False
                    route.rejection_reason = (
                        f"找不到存活的敌人「{route.move_target}」。"
                        f"当前敌人：{'、'.join(living) or '无'}"
                    )
                    return route
                resolved = resolve_fuzzy_name(route.move_target, living)
                if resolved:
                    route.move_target = resolved
                if route.move_meters <= 0:
                    route.approved = False
                    route.rejection_reason = "请说明移动米数（move_meters）。"
                    return route
                combat = game_state.combat
                if combat and route.move_meters > combat.movement_remaining_m:
                    route.approved = False
                    route.rejection_reason = (
                        f"移动力不足：剩余 {combat.movement_remaining_m}m，"
                        f"无法移动 {route.move_meters}m。"
                    )
                    return route

            if route.combat_action == "dash":
                route.action_cost = "main"
                route.needs_roll = False
                route.roll_type = "none"

            if route.combat_action == "attack" and game_state.combat:
                from game.combat_range import attack_range_status
                from game.combat_targets import effective_enemy_distance
                from game.weapon_combat import resolve_weapon_profile

                _auto_fill_approach_move_for_attack(
                    route, character, game_state, user_input
                )

                combat = game_state.combat
                weapon = resolve_weapon_profile(character, route)
                dist = effective_enemy_distance(combat, route.attack_target)
                if route.move_meters > 0 and route.move_toward:
                    dist = max(0, dist - route.move_meters)
                elif route.move_meters > 0 and not route.move_toward:
                    dist = dist + route.move_meters
                in_range, _, note = attack_range_status(dist, weapon)
                if not in_range:
                    route.approved = False
                    route.rejection_reason = (
                        f"射程不足：{note}。"
                        f"可先移动（combat_action=move，不耗主要动作）或疾跑（dash）。"
                    )
                    return route
                if route.move_meters > 0:
                    move_target = route.move_target.strip() or route.attack_target
                    if route.move_meters > combat.movement_remaining_m:
                        route.approved = False
                        route.rejection_reason = (
                            f"移动力不足：剩余 {combat.movement_remaining_m}m，"
                            f"无法先移动 {route.move_meters}m 再攻击。"
                        )
                        return route
                    route.move_target = move_target

        if in_combat and route.item_usage == "purchase":
            route.approved = False
            route.rejection_reason = "战斗中无法进行购买，请战斗结束后再交易。"
            route.needs_roll = False
            route.roll_type = "none"
            return route

        if in_combat and route.item_usage == "pickup":
            combat = game_state.combat
            route.action_cost = "free"
            if combat and route.approved and not combat.has_free_interact():
                route.approved = False
                route.rejection_reason = "本回合免费物件互动已用尽，无法拾取。"
                return route

        if in_combat and route.item_usage == "use":
            from game.combat_item_use import combat_use_item_cost

            if route.combat_action != "attack":
                route.combat_action = "use_item"
            else:
                route.item_usage = "none"
            route.mode = "combat"
            if route.combat_action == "use_item":
                if route.referenced_items:
                    route.action_cost = combat_use_item_cost(
                        character,
                        route.referenced_items[0],
                        attack_target=route.attack_target,
                        is_throw=_input_implies_throw(user_input),
                    )
                else:
                    route.action_cost = "bonus"
            route.needs_roll = False
            route.roll_type = "none"
            combat = game_state.combat
            if combat and route.approved and route.combat_action == "use_item":
                if route.action_cost == "free" and not combat.has_free_interact():
                    route.approved = False
                    route.rejection_reason = (
                        "本回合免费物件互动已用尽，无法快速装备/收起该物品。"
                    )
                    return route
                if route.action_cost == "bonus" and not combat.has_bonus_action():
                    route.approved = False
                    throw_hint = (
                        "无法投掷该物品。"
                        if _input_implies_throw(user_input) or route.attack_target.strip()
                        else "无法使用该物品。"
                    )
                    route.rejection_reason = f"本回合附加动作已用尽，{throw_hint}"
                    return route
                if route.action_cost == "main" and not combat.has_main_action():
                    route.approved = False
                    route.rejection_reason = (
                        "本回合主要动作已用尽，无法使用该物品（查阅文档等复杂操作）。"
                    )
                    return route

        if in_combat and route.approved:
            main_actions = {
                "attack",
                "defend",
                "flee",
                "interact",
                "talk",
                "grapple",
                "shove",
                "help",
                "search",
                "dash",
            }
            wants_main = route.combat_action in main_actions or route.action_cost == "main"
            wants_bonus = (
                route.combat_action == "use_item" and route.action_cost == "bonus"
            ) or (route.action_cost == "bonus" and route.combat_action not in main_actions)
            wants_move = route.combat_action == "move" or route.move_meters > 0
            combat = game_state.combat
            free_uses = _free_interact_uses_for_route(
                character, route, user_input=user_input
            )
            if combat and free_uses > 1:
                route.approved = False
                route.rejection_reason = (
                    "每回合仅一次免费物件互动，无法同时完成多项"
                    "（如拾取 + 拔背包武器 + 快速装备）。请分回合进行。"
                )
                return route
            if combat and free_uses == 1 and not combat.has_free_interact():
                route.approved = False
                route.rejection_reason = (
                    "本回合免费物件互动已用尽，无法完成该行动"
                    "（拾取、拔武器或快速装备）。"
                )
                return route
            if combat and wants_main and wants_bonus:
                if not combat.has_main_action() and not combat.has_bonus_action():
                    route.approved = False
                    route.rejection_reason = (
                        "本回合主要动作与附加动作都已用尽，请输入「结束回合」。"
                    )
                    return route
                if not combat.has_main_action():
                    route.approved = False
                    route.rejection_reason = (
                        "本回合主要动作已用尽，无法同时完成需要主要动作的部分"
                        "（如射击/攻击）。可先拾取（免费互动），或输入「结束回合」。"
                    )
                    return route
                if not combat.has_bonus_action():
                    route.approved = False
                    route.rejection_reason = (
                        "本回合附加动作已用尽，无法同时使用物品。"
                        "请先完成攻击/主要动作，下回合再使用。"
                    )
                    return route

        if route.skill_usage == "use" or (
            route.skill_usage == "none" and route.referenced_skills
        ):
            for skill in route.referenced_skills:
                if not fuzzy_in_list(skill, character.skill_names()):
                    route.approved = False
                    route.rejection_reason = f"你没有「{skill}」这项技能，无法执行该行动。"
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route
                matched = character.find_skill(skill)
                if matched and matched.kind == "passive":
                    route.approved = False
                    route.rejection_reason = (
                        f"「{matched.name}」是被动技能，无法主动施展；"
                        "其效果已常驻生效，请直接描述你想做的行动。"
                    )
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route
            if route.skill_usage == "use":
                route.proficiency_bonus = True

        if route.skill_usage == "learn":
            for skill in route.referenced_skills:
                if fuzzy_in_list(skill, character.skill_names()):
                    route.approved = False
                    route.rejection_reason = f"你已经掌握「{skill}」，无需再学习。"
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route

        if route.item_usage == "use":
            for item in route.referenced_items:
                if not character.has_inventory_item(item):
                    route.approved = False
                    route.rejection_reason = f"你的背包中没有「{item}」，无法使用该物品。"
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route

        if route.item_usage == "purchase":
            if not route.referenced_items:
                route.approved = False
                route.rejection_reason = "购买行动须指明获得的物品（referenced_items）。"
                return route
            if not route.payment_items:
                route.approved = False
                route.rejection_reason = "购买行动须指明支付物品（payment_items）。"
                route.needs_roll = False
                route.roll_type = "none"
                return route
            quantity = max(1, route.payment_quantity or 1)
            for payment in route.payment_items:
                if not _payment_available(character, payment):
                    route.approved = False
                    route.rejection_reason = (
                        f"你的背包中没有可用于支付的「{payment}」。"
                    )
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route
                if not _payment_sufficient(character, payment, quantity):
                    target = character.find_inventory_item(payment)
                    label = target.display() if target else payment
                    route.approved = False
                    route.rejection_reason = (
                        f"支付数量不足：需要 {quantity}，背包中仅有 {label}。"
                    )
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route

        if in_combat and route.approved and route.needs_roll:
            if route.roll_type == "ability_check":
                if route.ability not in ABILITY_FIELDS:
                    route.approved = False
                    route.rejection_reason = "行动裁定异常（无效属性），请重新描述。"
                    return route
                if not ensure_ability_check_dc(route):
                    route.approved = False
                    route.rejection_reason = "行动裁定异常（缺少合法 DC），请重新描述。"
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route
            else:
                route.needs_roll = False
                route.roll_type = "none"

        if not in_combat and route.needs_roll:
            if route.roll_type == "ability_check":
                if route.ability not in ABILITY_FIELDS:
                    route.approved = False
                    route.rejection_reason = "行动裁定异常（无效属性），请重新描述你的行动。"
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route
                if not ensure_ability_check_dc(route):
                    route.approved = False
                    route.rejection_reason = "行动裁定异常（缺少合法 DC），请重新描述你的行动。"
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route
            elif route.roll_type == "dice":
                if not route.dice_notation:
                    route.approved = False
                    route.rejection_reason = "行动裁定异常（缺少掷骰表达式），请重新描述你的行动。"
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route
            else:
                route.approved = False
                route.rejection_reason = (
                    "行动裁定异常（缺少掷骰类型），请重新描述你的行动。"
                )
                route.needs_roll = False
                route.roll_type = "none"
                return route

        if not route.needs_roll:
            route.proficiency_bonus = False

        return route
