"""为物品/技能生成 effects 数值（AI 判断是否战斗相关）。"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.effects import EntityEffects
from game.models import Character
from game.scenario import Scenario
from game.stat_forge import (
    ForgeTarget,
    apply_entity_effects,
    mark_entity_skipped,
)

logger = logging.getLogger(__name__)


class StatForgeAgent:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.2)
        system_prompt = (PROMPTS_DIR / "stat_forge.txt").read_text(encoding="utf-8")
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【世界观】\nworld_id={world_id}\n\n"
                    "【角色背景】\n{background}\n\n"
                    "【待裁定实体】\n{targets_json}\n\n"
                    "请输出 JSON：",
                ),
            ]
        )

    async def aforge(
        self,
        character: Character,
        scenario: Scenario,
        targets: list[ForgeTarget],
    ) -> list[str]:
        if not targets:
            return []

        import json

        targets_payload = [
            {
                "kind": target.kind,
                "name": target.name,
                "description": target.description,
            }
            for target in targets
        ]
        chain = self.prompt | self.llm
        response = await chain.ainvoke(
            {
                "world_id": scenario.world_id or "modern",
                "background": character.background.strip() or "（无）",
                "targets_json": json.dumps(targets_payload, ensure_ascii=False, indent=2),
            }
        )
        parsed = self._parse_entities((response.content or "").strip())
        if not parsed:
            logger.warning("StatForge 未返回有效 JSON，本轮不写入（下轮重试）")
            return []

        events: list[str] = []
        for target in targets:
            key = (target.kind, target.name)
            if key not in parsed:
                events.append(mark_entity_skipped(character, target))
                continue
            decision = parsed[key]
            if decision == "skip":
                events.append(mark_entity_skipped(character, target))
                continue
            events.append(
                apply_entity_effects(
                    character,
                    target,
                    decision,
                    world_id=scenario.world_id or "",
                )
            )
        return events

    @staticmethod
    def _parse_entities(
        text: str,
    ) -> dict[tuple[str, str], EntityEffects | Literal["skip"]]:
        data = extract_json_dict(text)
        if not isinstance(data, dict):
            return {}

        result: dict[tuple[str, str], EntityEffects | Literal["skip"]] = {}
        for item in data.get("entities") or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "item").strip().lower()
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            if item.get("skip") is True:
                result[(kind, name)] = "skip"
                continue
            raw_effects = item.get("effects")
            if not isinstance(raw_effects, dict):
                continue
            try:
                result[(kind, name)] = EntityEffects.model_validate(raw_effects)
            except (TypeError, ValueError):
                continue
        return result
