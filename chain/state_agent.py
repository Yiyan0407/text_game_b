import logging

from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.models import Character, ChatMessage, GameState
from game.results import ActionRouteResult, StatePatch
from game.narrative_time import format_player_stated_duration_hint
from game.state_patch import patch_from_dict

logger = logging.getLogger(__name__)


def _format_recent_history(history: list[ChatMessage], limit: int = 6) -> str:
    if not history:
        return "（无）"
    recent = history[-limit:]
    lines = []
    for msg in recent:
        role = {"user": "玩家", "assistant": "KP", "system": "系统"}.get(msg.role, msg.role)
        lines.append(f"[{role}] {msg.content}")
    return "\n".join(lines)


def _format_mechanical_events(events: list[str]) -> str:
    if not events:
        return "（无）"
    return "\n".join(f"- {event}" for event in events)


def _format_route_summary(route: ActionRouteResult | None) -> str:
    if route is None:
        return "（无路由，开场模式）"
    lines = [
        f"行动意图：{route.action_intent}",
        f"叙事边界：{route.scope_stop}",
        f"模式：{route.mode}",
        f"物品用途：{route.item_usage}",
        f"技能用途：{route.skill_usage}",
    ]
    if route.referenced_items:
        lines.append(f"涉及物品：{', '.join(route.referenced_items)}")
    if route.referenced_skills:
        lines.append(f"涉及技能：{', '.join(route.referenced_skills)}")
    if route.skill_usage == "learn":
        lines.append("（学习技能：仅检定成功或 NPC 同意时可 add）")
    return "\n".join(lines)


class StateAgent:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.2)
        system_prompt = (PROMPTS_DIR / "state_agent.txt").read_text(encoding="utf-8")
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【游戏状态】\n{game_state_context}\n\n"
                    "【玩家角色】\n"
                    "姓名：{character_name}\n"
                    "背景：{character_background}\n"
                    "属性：{character_abilities}\n"
                    "背包：{character_inventory}\n"
                    "装备：{character_equipment}\n"
                    "持用：{character_active_gear}\n"
                    "技能：{character_skills}\n\n"
                    "【路由裁定】\n{route_summary}\n\n"
                    "【机械结算结果】\n{mechanical_events}\n\n"
                    "【玩家声称耗时（须自行裁定是否合理）】\n{player_stated_duration}\n\n"
                    "【最近对话】\n{recent_history}\n\n"
                    "【玩家行动/指令】\n{user_input}\n\n"
                    "请输出状态补丁 JSON：",
                ),
            ]
        )

    def propose(
        self,
        user_input: str,
        character: Character,
        game_state: GameState,
        mechanical_events: list[str],
        history: list[ChatMessage],
        route: ActionRouteResult | None = None,
    ) -> StatePatch:
        chain = self.prompt | self.llm
        response = chain.invoke(self._build_inputs(
            user_input, character, game_state, mechanical_events, history, route
        ))
        return self._parse_response((response.content or "").strip())

    async def apropose(
        self,
        user_input: str,
        character: Character,
        game_state: GameState,
        mechanical_events: list[str],
        history: list[ChatMessage],
        route: ActionRouteResult | None = None,
    ) -> StatePatch:
        chain = self.prompt | self.llm
        response = await chain.ainvoke(self._build_inputs(
            user_input, character, game_state, mechanical_events, history, route
        ))
        return self._parse_response((response.content or "").strip())

    def _build_inputs(
        self,
        user_input: str,
        character: Character,
        game_state: GameState,
        mechanical_events: list[str],
        history: list[ChatMessage],
        route: ActionRouteResult | None,
    ) -> dict:
        return {
            "game_state_context": game_state.format_for_prompt(),
            "character_name": character.name,
            "character_background": character.background.strip() or "（未填写）",
            "character_abilities": character.format_abilities(),
            "character_inventory": character.format_inventory(),
            "character_equipment": character.format_equipment(),
            "character_active_gear": character.format_active_gear(),
            "character_skills": character.format_skills(),
            "route_summary": _format_route_summary(route),
            "mechanical_events": _format_mechanical_events(mechanical_events),
            "recent_history": _format_recent_history(history),
            "player_stated_duration": format_player_stated_duration_hint(user_input),
            "user_input": user_input.strip(),
        }

    @staticmethod
    def _parse_response(text: str) -> StatePatch:
        data = extract_json_dict(text)
        if data is not None:
            try:
                return patch_from_dict(data)
            except (TypeError, ValueError):
                logger.warning("状态补丁 JSON 字段异常: %s", text[:500])
        else:
            logger.warning("状态补丁 JSON 解析失败: %s", text[:500] or "（空响应）")
        return StatePatch()
