"""为单个开战敌人生成 enemy_defs 数值（可并发）。"""

from __future__ import annotations

import json
import logging

from langchain_core.prompts import ChatPromptTemplate

from chain.async_utils import gather_best_effort
from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.enemy_forge import (
    EnemyForgeTarget,
    collect_enemy_forge_targets,
    format_enemy_forge_event,
    is_valid_enemy_def,
    merge_enemy_defs,
    names_from_enemies_spec,
)
from game.models import Character, GameState
from game.results import ActionRouteResult, EnemyDefPatch
from game.scenario import Scenario

logger = logging.getLogger(__name__)


class EnemyForgeAgent:
    def __init__(self):
        self.llm = create_chat_llm(role="default", temperature=0.2)
        system_prompt = (PROMPTS_DIR / "enemy_forge.txt").read_text(encoding="utf-8")
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【世界观】\nworld_id={world_id}\n"
                    "【模组】\n{scenario_context}\n\n"
                    "【玩家】\n{background}\n\n"
                    "【最近叙事】\n{narrative_context}\n\n"
                    "【已生成参照（同场其他敌人，横向一致）】\n"
                    "{reference_json}\n\n"
                    "【待生成敌人】\nname={enemy_name}\n"
                    "description={enemy_description}\n\n"
                    "请输出 JSON：",
                ),
            ]
        )

    async def aforge_one(
        self,
        target: EnemyForgeTarget,
        *,
        character: Character,
        scenario: Scenario,
        narrative_context: str = "",
        reference_defs: list[EnemyDefPatch] | None = None,
    ) -> EnemyDefPatch | None:
        refs = reference_defs or []
        reference_payload = [
            {
                "name": item.name,
                "hp": item.hp,
                "ac": item.ac,
                "attack_damage": item.attack_damage,
                "sp": item.sp,
            }
            for item in refs
            if is_valid_enemy_def(item)
        ]
        chain = self.prompt | self.llm
        response = await chain.ainvoke(
            {
                "world_id": scenario.world_id or "modern",
                "scenario_context": scenario.format_for_prompt(),
                "background": character.background.strip() or "（无）",
                "narrative_context": narrative_context.strip() or "（无）",
                "reference_json": json.dumps(
                    reference_payload if reference_payload else [{"note": "（尚无参照）"}],
                    ensure_ascii=False,
                    indent=2,
                ),
                "enemy_name": target.name,
                "enemy_description": target.description.strip() or "（无额外描述）",
            }
        )
        return self._parse_enemy((response.content or "").strip(), expected_name=target.name)

    async def aensure_combat_enemy_defs(
        self,
        route: ActionRouteResult,
        *,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        narrative_context: str = "",
    ) -> tuple[list[EnemyDefPatch], list[str]]:
        if not route.trigger_combat:
            return route.enemy_defs, []

        targets, kept = collect_enemy_forge_targets(route, game_state)
        if not targets:
            expected = names_from_enemies_spec(route.enemies_spec)
            merged = merge_enemy_defs(kept, [], expected_names=expected or None)
            return merged, []

        forged_results = await gather_best_effort(
            *[
                self.aforge_one(
                    target,
                    character=character,
                    scenario=scenario,
                    narrative_context=narrative_context,
                    reference_defs=kept,
                )
                for target in targets
            ]
        )
        forged = [item for item in forged_results if isinstance(item, EnemyDefPatch)]
        expected = names_from_enemies_spec(route.enemies_spec)
        merged = merge_enemy_defs(kept, forged, expected_names=expected or None)
        events = [format_enemy_forge_event(item) for item in forged if is_valid_enemy_def(item)]
        if targets and not forged:
            logger.warning("EnemyForge 全部失败，将回退 enemies_spec / 敌对 NPC")
        return merged, events

    @staticmethod
    def _parse_enemy(text: str, *, expected_name: str) -> EnemyDefPatch | None:
        data = extract_json_dict(text)
        if not isinstance(data, dict):
            return None
        raw = data.get("enemy") if isinstance(data.get("enemy"), dict) else data
        if not isinstance(raw, dict):
            return None
        if not str(raw.get("name") or "").strip():
            raw = {**raw, "name": expected_name}
        try:
            patch = EnemyDefPatch.model_validate(raw)
        except (TypeError, ValueError):
            return None
        if not is_valid_enemy_def(patch):
            return None
        return patch
