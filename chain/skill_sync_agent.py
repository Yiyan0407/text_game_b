"""KP 叙事后的技能同步 Agent。"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate

from chain.agent_context import (
    format_character_block,
    format_mechanical_events,
    format_route_summary,
)
from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.models import Character, ChatMessage, GameState
from game.results import ActionRouteResult, StatePatch
from game.state_patch import patch_from_dict

logger = logging.getLogger(__name__)


class SkillSyncAgent:
    def __init__(self):
        self.llm = create_chat_llm(role="skill_sync", temperature=0.2)
        system_prompt = (PROMPTS_DIR / "skill_sync_agent.txt").read_text(encoding="utf-8")
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【游戏状态】\n{game_state_context}\n\n"
                    "【玩家角色】\n"
                    "姓名：{character_name}\n"
                    "技能：{character_skills}\n\n"
                    "【路由裁定】\n{route_summary}\n\n"
                    "【机械结算结果】\n{mechanical_events}\n\n"
                    "【玩家行动/指令】\n{user_input}\n\n"
                    "【本回合 KP 叙事】\n{kp_narrative}\n\n"
                    "请输出技能补丁 JSON：",
                ),
            ]
        )

    async def apropose(
        self,
        user_input: str,
        kp_narrative: str,
        character: Character,
        game_state: GameState,
        mechanical_events: list[str],
        route: ActionRouteResult | None = None,
    ) -> StatePatch:
        chain = self.prompt | self.llm
        response = await chain.ainvoke(
            self._build_inputs(
                user_input,
                kp_narrative,
                character,
                game_state,
                mechanical_events,
                route,
            )
        )
        return self._parse_response((response.content or "").strip())

    def _build_inputs(
        self,
        user_input: str,
        kp_narrative: str,
        character: Character,
        game_state: GameState,
        mechanical_events: list[str],
        route: ActionRouteResult | None,
    ) -> dict:
        inputs = format_character_block(character)
        inputs.update(
            {
                "game_state_context": game_state.format_for_prompt(),
                "route_summary": format_route_summary(route),
                "mechanical_events": format_mechanical_events(mechanical_events),
                "user_input": user_input.strip(),
                "kp_narrative": kp_narrative.strip() or "（无）",
            }
        )
        return inputs

    @staticmethod
    def _parse_response(text: str) -> StatePatch:
        data = extract_json_dict(text)
        if data is not None:
            try:
                full = patch_from_dict(data)
                return StatePatch(skills=list(full.skills))
            except (TypeError, ValueError):
                logger.warning("技能同步补丁 JSON 字段异常: %s", text[:500])
        else:
            logger.warning("技能同步补丁 JSON 解析失败: %s", text[:500] or "（空响应）")
        return StatePatch()
