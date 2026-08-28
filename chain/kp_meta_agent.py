"""KP meta 沟通 Agent：处理 【kp】 前缀的出戏申诉与状态回退。"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from chain.agent_context import (
    format_character_block,
    format_recent_history,
    format_recent_system_events,
)
from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.models import Character, ChatMessage, GameState
from game.results import StatePatch
from game.state_patch import patch_from_dict, sanitize_kp_meta_patch

logger = logging.getLogger(__name__)


class KpMetaResult(BaseModel):
    response: str = ""
    patch: StatePatch = Field(default_factory=StatePatch)
    character_hp: int | None = None


class KpMetaAgent:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.2)
        system_prompt = (PROMPTS_DIR / "kp_meta_agent.txt").read_text(encoding="utf-8")
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【游戏状态】\n{game_state_context}\n\n"
                    "【玩家角色】\n"
                    "姓名：{character_name}\n"
                    "背景：{character_background}\n"
                    "HP：{character_hp}/{character_max_hp}\n"
                    "背包：{character_inventory}\n"
                    "装备：{character_equipment}\n\n"
                    "【最近对话】\n{recent_history}\n\n"
                    "【最近系统/机械结算 — 申诉裁定优先参考】\n{recent_system_events}\n\n"
                    "【玩家 KP 沟通】\n{meta_message}\n\n"
                    "请输出 JSON（含 response，必要时含 patch / character_hp）：",
                ),
            ]
        )

    async def arespond(
        self,
        meta_message: str,
        character: Character,
        game_state: GameState,
        history: list[ChatMessage],
    ) -> KpMetaResult:
        chain = self.prompt | self.llm
        response = await chain.ainvoke(self._build_inputs(meta_message, character, game_state, history))
        return self._parse_response((response.content or "").strip())

    def respond(
        self,
        meta_message: str,
        character: Character,
        game_state: GameState,
        history: list[ChatMessage],
    ) -> KpMetaResult:
        chain = self.prompt | self.llm
        response = chain.invoke(self._build_inputs(meta_message, character, game_state, history))
        return self._parse_response((response.content or "").strip())

    def _build_inputs(
        self,
        meta_message: str,
        character: Character,
        game_state: GameState,
        history: list[ChatMessage],
    ) -> dict:
        inputs = format_character_block(character)
        inputs.update(
            {
                "game_state_context": game_state.format_for_prompt(),
                "character_hp": str(character.hp),
                "character_max_hp": str(character.max_hp),
                "recent_history": format_recent_history(history, limit=20),
                "recent_system_events": format_recent_system_events(history, limit=15),
                "meta_message": meta_message.strip(),
            }
        )
        return inputs

    @staticmethod
    def _parse_response(text: str) -> KpMetaResult:
        data = extract_json_dict(text)
        if data is None:
            logger.warning("KP meta JSON 解析失败: %s", text[:500] or "（空响应）")
            cleaned = text.strip()
            if cleaned:
                return KpMetaResult(response=cleaned)
            return KpMetaResult(response="收到，但我未能解析处理结果，请再描述一下问题。")

        response = str(data.get("response", "")).strip()
        patch = sanitize_kp_meta_patch(_extract_patch_from_kp_meta(data))

        hp_value: int | None = None
        character_hp = data.get("character_hp")
        if character_hp is not None:
            try:
                hp_value = int(character_hp)
            except (TypeError, ValueError):
                hp_value = None

        if not response:
            response = "已记录你的反馈。"
        return KpMetaResult(response=response, patch=patch, character_hp=hp_value)


def _extract_patch_from_kp_meta(data: dict) -> StatePatch:
    """合并 patch 嵌套与顶层字段（LLM 常省略 patch 包装）。"""
    payload = {
        key: value
        for key, value in data.items()
        if key not in ("response", "character_hp")
    }
    nested = payload.pop("patch", None)
    if isinstance(nested, dict):
        merged = {**payload, **nested}
    else:
        merged = payload
    if not merged:
        return StatePatch()
    try:
        return patch_from_dict(merged)
    except (TypeError, ValueError):
        logger.warning("KP meta patch 字段异常: %s", str(merged)[:500])
        return StatePatch()
