"""KP 叙事前的世界状态 Agent（场景/NPC/任务/时间/记忆等）。"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate

from chain.agent_context import (
    format_character_block,
    format_mechanical_events,
    format_recent_history,
    format_route_summary,
)
from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.models import Character, ChatMessage, GameState
from game.narrative_time import format_player_stated_duration_hint
from game.results import ActionRouteResult, StatePatch
from game.state_patch import patch_from_dict

logger = logging.getLogger(__name__)


class WorldStateAgent:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.2)
        system_prompt = (PROMPTS_DIR / "world_state_agent.txt").read_text(encoding="utf-8")
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
                    "请输出世界状态补丁 JSON（勿含 inventory add / equipment equip）：",
                ),
            ]
        )

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
        response = await chain.ainvoke(
            self._build_inputs(user_input, character, game_state, mechanical_events, history, route)
        )
        return self._parse_response((response.content or "").strip())

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
        response = chain.invoke(
            self._build_inputs(user_input, character, game_state, mechanical_events, history, route)
        )
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
        inputs = format_character_block(character)
        inputs.update(
            {
                "game_state_context": game_state.format_for_prompt(),
                "route_summary": format_route_summary(route),
                "mechanical_events": format_mechanical_events(mechanical_events),
                "recent_history": format_recent_history(history),
                "player_stated_duration": format_player_stated_duration_hint(user_input),
                "user_input": user_input.strip(),
            }
        )
        return inputs

    @staticmethod
    def _parse_response(text: str) -> StatePatch:
        data = extract_json_dict(text)
        if data is not None:
            try:
                patch = patch_from_dict(data)
                return _strip_pre_kp_item_fields(patch)
            except (TypeError, ValueError):
                logger.warning("世界状态补丁 JSON 字段异常: %s", text[:500])
        else:
            logger.warning("世界状态补丁 JSON 解析失败: %s", text[:500] or "（空响应）")
        return StatePatch()


def _strip_pre_kp_item_fields(patch: StatePatch) -> StatePatch:
    """KP 前阶段丢弃 add/equip，仅保留 remove/unequip（由 ItemSync 负责增与装）。"""
    patch.inventory = [inv for inv in patch.inventory if inv.action == "remove"]
    patch.equipment = [eq for eq in patch.equipment if eq.action == "unequip"]
    return patch
