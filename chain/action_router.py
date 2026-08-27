import logging
import re

from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.models import ABILITY_FIELDS, Character, ChatMessage, GameState
from game.results import ActionRouteResult
from game.scenario import Scenario
from prompts.templates import load_world_prompt


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())


def _fuzzy_in_list(name: str, items: list[str]) -> bool:
    normalized = _normalize_name(name)
    if not normalized:
        return False
    for item in items:
        item_norm = _normalize_name(item)
        if normalized == item_norm or normalized in item_norm or item_norm in normalized:
            return True
    return False


def _payment_available(character: Character, payment: str) -> bool:
    return character.has_inventory_item(payment)


def _format_recent_history(history: list[ChatMessage], limit: int = 6) -> str:
    if not history:
        return "（无）"
    recent = history[-limit:]
    lines = []
    for msg in recent:
        role = {"user": "玩家", "assistant": "KP", "system": "系统"}.get(msg.role, msg.role)
        lines.append(f"[{role}] {msg.content}")
    return "\n".join(lines)


COMPOUND_ACTION_MARKERS = (
    "然后",
    "接着",
    "之后",
    "再去",
    "再回",
    "再去找",
    "顺便",
    "并且还要",
    "并且",
    "还要",
    "完成后",
)

VAGUE_DESTINATION_PHRASES = (
    "去现场",
    "到现场",
    "直接去",
    "去那边",
    "过去看看",
    "去一趟",
    "实地考察",
    "现场看看",
)

VAGUE_DESTINATION_REJECTION_MARKERS = (
    "目标不明确",
    "具体地点",
    "明确具体",
    "目的地不明确",
)

CORP_DESTINATION_SIGNALS = (
    "星辰科技",
    "目标公司",
    "邮件服务器",
    "邮件信头",
    "信头",
    "核实邮件",
    "确认这些邮件",
    "内部的人",
    "作证",
)

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
    "隐匿",
    "悄悄",
    "渗透",
    "非法进入",
    "溜入",
    "摸进",
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
    "公司",
    "内部",
    "监控",
)


def _looks_like_compound_action(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return any(marker in normalized for marker in COMPOUND_ACTION_MARKERS)


def _looks_like_vague_destination_action(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return any(marker in normalized for marker in VAGUE_DESTINATION_PHRASES)


def _looks_like_vague_destination_rejection(reason: str) -> bool:
    return any(marker in reason for marker in VAGUE_DESTINATION_REJECTION_MARKERS)


def _corp_destination_node(scenario: Scenario):
    for node in scenario.key_nodes:
        if node.id == "corp_lobby" or "公司" in node.title:
            return node
    return None


def _recent_context_text(history: list[ChatMessage], scenario: Scenario, limit: int = 8) -> str:
    parts = [_format_recent_history(history, limit=limit), scenario.format_for_prompt()]
    return "\n".join(parts)


def _looks_like_infiltration_action(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return any(marker in normalized for marker in INFILTRATION_ACTION_MARKERS)


def _looks_like_restricted_area(context: str) -> bool:
    return any(signal in context for signal in RESTRICTED_AREA_SIGNALS)


logger = logging.getLogger(__name__)

_PARSE_FAILURE_REASON = "行动裁定解析失败，请重新描述你的行动。"


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
        "interact", "talk", "grapple", "shove", "help", "search", "end_turn",
    }
    if combat_action not in valid_actions:
        combat_action = "none"
    action_cost = data.get("action_cost", "main")
    if action_cost not in ("main", "bonus", "free"):
        action_cost = "main"
    approved = data.get("approved", False)
    if isinstance(approved, str):
        approved = approved.strip().lower() in ("true", "1", "yes", "是", "批准", "通过")
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
        action_intent=str(data.get("action_intent", "")).strip(),
        scope_stop=str(data.get("scope_stop", "")).strip(),
        must_not_narrate=_coerce_str_list(data.get("must_not_narrate")),
        mode=mode,
        trigger_combat=bool(data.get("trigger_combat", False)),
        enemies_spec=str(data.get("enemies_spec", "")).strip(),
        combat_action=combat_action,
        action_cost=action_cost,
        attack_target=str(data.get("attack_target", "")).strip(),
        ends_turn=bool(data.get("ends_turn", False)),
    )


class ActionRouter:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.2)
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
                    "技能：{character_skills}\n\n"
                    "【最近对话】\n{recent_history}\n\n"
                    "【玩家行动】\n{user_input}\n\n"
                    "请输出裁定 JSON：",
                ),
            ]
        )

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
            {
                "world_rules": load_world_prompt(scenario.world_id),
                "scenario_context": scenario.format_for_prompt(),
                "game_state_context": game_state.format_for_prompt(),
                "character_name": character.name,
                "character_background": character.background,
                "character_abilities": character.format_abilities(),
                "hp": character.hp,
                "max_hp": character.max_hp,
                "character_inventory": character.format_inventory(),
                "character_skills": character.format_skills(),
                "recent_history": _format_recent_history(history),
                "user_input": user_input.strip(),
            }
        )
        text = (response.content or "").strip()
        route = self._parse_route(text)
        if not route.approved and route.rejection_reason == _PARSE_FAILURE_REASON:
            route = self._fallback_route(user_input.strip(), game_state)
        route = self.validate(route, character, game_state)
        route = self._maybe_rescue_vague_destination(
            route, user_input.strip(), history, scenario
        )
        route = self._maybe_require_infiltration_roll(
            route, user_input.strip(), history
        )
        return self._apply_granularity(route, user_input.strip())

    @staticmethod
    def _maybe_rescue_vague_destination(
        route: ActionRouteResult,
        user_input: str,
        history: list[ChatMessage],
        scenario: Scenario,
    ) -> ActionRouteResult:
        if route.approved:
            return route
        if not _looks_like_vague_destination_action(user_input):
            return route
        if not _looks_like_vague_destination_rejection(route.rejection_reason):
            return route

        context = _recent_context_text(history, scenario)
        if not any(signal in context for signal in CORP_DESTINATION_SIGNALS):
            return route

        corp_node = _corp_destination_node(scenario)
        route.approved = True
        route.rejection_reason = ""
        if not route.action_intent:
            if corp_node:
                route.action_intent = f"前往{corp_node.title}实地核实邮件线索"
            else:
                route.action_intent = "前往对话中指向的目标公司现场核实线索"
        if not route.scope_stop:
            destination = corp_node.title if corp_node else "目标现场"
            route.scope_stop = f"抵达{destination}或完成外围接触，尚未深入完成全部调查"
        if not route.must_not_narrate:
            route.must_not_narrate = [
                "深入公司内部或完成全部取证",
                "与其他 NPC 的会面或长段情报灌输",
                "未在本行动范围内触发的任务奖励或系统回馈",
            ]
        return route

    @staticmethod
    def _maybe_require_infiltration_roll(
        route: ActionRouteResult,
        user_input: str,
        history: list[ChatMessage],
    ) -> ActionRouteResult:
        if not route.approved or route.mode != "exploration" or route.needs_roll:
            return route
        if not _looks_like_infiltration_action(user_input):
            return route
        context = _format_recent_history(history, limit=8)
        if not _looks_like_restricted_area(context):
            return route
        route.needs_roll = True
        route.roll_type = "ability_check"
        route.ability = "dex"
        route.dc = 16 if any(x in context for x in ("巡逻", "安保", "监控", "门禁")) else 14
        if not route.action_intent:
            route.action_intent = user_input.strip()
        return route

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
    def _fallback_route(user_input: str, game_state: GameState) -> ActionRouteResult:
        if game_state.is_in_combat() or not user_input.strip():
            return ActionRouteResult(
                approved=False,
                rejection_reason=_PARSE_FAILURE_REASON,
            )
        return ActionRouteResult(
            approved=True,
            action_intent=user_input.strip(),
            scope_stop="玩家本句回应的直接结果达成时",
            must_not_narrate=[
                "玩家未提及的后续移动或场景切换",
                "与其他 NPC 的会面或长段情报灌输",
            ],
        )

    @staticmethod
    def validate(
        route: ActionRouteResult,
        character: Character,
        game_state: GameState,
    ) -> ActionRouteResult:
        in_combat = game_state.is_in_combat()

        if in_combat:
            route.mode = "combat"
            route.trigger_combat = False
            combat = game_state.combat
            if combat and route.approved and not combat.is_player_turn():
                actor = combat.current_actor()
                label = "玩家" if actor == "player" else actor
                route.approved = False
                route.rejection_reason = f"还没轮到你，当前是 {label} 的回合。"
                return route
            if combat and route.approved and route.combat_action not in ("none", "end_turn"):
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
            mechanical_actions = {"attack", "defend", "flee", "help", "end_turn", "use_item"}
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

        if in_combat or route.trigger_combat:
            if route.combat_action == "attack" and route.attack_target:
                living = game_state.combat.living_enemy_names() if game_state.combat else []
                if route.trigger_combat:
                    living = [
                        part.split(":")[0].strip()
                        for part in route.enemies_spec.split(",")
                        if part.strip()
                    ]
                if living and not _fuzzy_in_list(route.attack_target, living):
                    route.approved = False
                    route.rejection_reason = (
                        f"找不到存活的敌人「{route.attack_target}」。"
                        f"当前敌人：{'、'.join(living) or '无'}"
                    )
                    return route

        if route.skill_usage == "use" or (
            route.skill_usage == "none" and route.referenced_skills
        ):
            for skill in route.referenced_skills:
                if not _fuzzy_in_list(skill, character.skills):
                    route.approved = False
                    route.rejection_reason = f"你没有「{skill}」这项技能，无法执行该行动。"
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route

        if route.skill_usage == "learn":
            for skill in route.referenced_skills:
                if _fuzzy_in_list(skill, character.skills):
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
            if route.payment_items:
                for payment in route.payment_items:
                    if not _payment_available(character, payment):
                        route.approved = False
                        route.rejection_reason = (
                            f"你的背包中没有可用于支付的「{payment}」。"
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
                if route.dc < 1:
                    route.dc = 14
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
                if route.dc < 1:
                    route.dc = 14
            elif route.roll_type == "dice":
                if not route.dice_notation:
                    route.approved = False
                    route.rejection_reason = "行动裁定异常（缺少掷骰表达式），请重新描述你的行动。"
                    route.needs_roll = False
                    route.roll_type = "none"
                    return route
            else:
                route.roll_type = "ability_check"
                if route.ability not in ABILITY_FIELDS:
                    route.ability = "cha"
                if route.dc < 1:
                    route.dc = 14

        if not route.action_intent:
            route.action_intent = "执行玩家描述的行动"

        return route

    @staticmethod
    def _apply_granularity(route: ActionRouteResult, user_input: str) -> ActionRouteResult:
        if not route.approved:
            return route
        if route.mode == "exploration" and _looks_like_compound_action(user_input):
            route.approved = False
            route.rejection_reason = (
                "请一次只描述一个行动。你似乎计划了多个步骤，请先输入当前这一步。"
            )
            return route
        ActionRouter._finalize_scope(route)
        return route

    @staticmethod
    def _finalize_scope(route: ActionRouteResult) -> None:
        if not route.scope_stop:
            route.scope_stop = f"「{route.action_intent}」的直接结果达成时"
        if not route.must_not_narrate:
            route.must_not_narrate = [
                "玩家未提及的后续移动或场景切换",
                "与其他 NPC 的会面或长段情报灌输",
                "未在本行动范围内触发的任务奖励或系统回馈",
            ]
