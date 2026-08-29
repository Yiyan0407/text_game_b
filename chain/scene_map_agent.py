"""场景地图 Agent：场景变更后增量更新 JSON 拓扑图。"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate

from chain.agent_context import format_recent_history
from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR, get_settings
from game.models import ChatMessage, GameState
from game.scene_map import apply_map_update, format_map_context
from game.scenario import Scenario

logger = logging.getLogger(__name__)


class SceneMapAgent:
    def __init__(self):
        self.llm = create_chat_llm(role="scene_map", temperature=0.2)
        system_prompt = (PROMPTS_DIR / "scene_map_agent.txt").read_text(encoding="utf-8")
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【模组】\n{scenario_title}\n{scenario_world}\n\n"
                    "【地图上下文】\n{map_context}\n\n"
                    "【最近对话】\n{recent_history}\n\n"
                    "请输出更新后的场景地图 JSON（nodes + edges）：",
                ),
            ]
        )

    async def aupdate(
        self,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
        *,
        travel_from: str = "",
    ) -> bool:
        if not get_settings().enable_scene_map:
            return False
        if not get_settings().openai_api_key:
            return False
        chain = self.prompt | self.llm
        response = await chain.ainvoke(
            {
                "scenario_title": scenario.title,
                "scenario_world": scenario.world or scenario.description,
                "map_context": format_map_context(
                    game_state, scenario, travel_from=travel_from
                ),
                "recent_history": format_recent_history(history, limit=12),
            }
        )
        return self._apply_response(game_state, scenario, (response.content or "").strip())

    def update(
        self,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
        *,
        travel_from: str = "",
    ) -> bool:
        if not get_settings().enable_scene_map:
            return False
        if not get_settings().openai_api_key:
            return False
        chain = self.prompt | self.llm
        response = chain.invoke(
            {
                "scenario_title": scenario.title,
                "scenario_world": scenario.world or scenario.description,
                "map_context": format_map_context(
                    game_state, scenario, travel_from=travel_from
                ),
                "recent_history": format_recent_history(history, limit=12),
            }
        )
        return self._apply_response(game_state, scenario, (response.content or "").strip())

    @staticmethod
    def _apply_response(game_state: GameState, scenario: Scenario, text: str) -> bool:
        data = extract_json_dict(text)
        if not isinstance(data, dict):
            logger.warning("场景地图 JSON 解析失败: %s", text[:500] or "（空响应）")
            return False
        if not apply_map_update(game_state, data, scenario):
            logger.warning("场景地图 JSON 无效或缺少 nodes")
            return False
        return True
