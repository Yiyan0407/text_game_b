"""回合流水线：路由 → 机械 → 世界状态 → KP → 物品同步 → 异步收尾。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from chain.action_router import ActionRouter
from chain.agent_context import format_recent_history
from chain.async_utils import gather_best_effort
from chain.item_sync_agent import ItemSyncAgent
from chain.kp_chain import KPChain
from chain.memory import ConversationWindowMemory
from chain.memory_manager import LongTermMemoryManager
from chain.stat_forge_agent import StatForgeAgent
from chain.suggestions import ActionSuggester
from chain.world_state_agent import WorldStateAgent
from config.settings import get_settings
from game.game_config import apply_guidance_hint
from game.models import Character, GameState
from game.narrative_brief import (
    build_narrative_brief_static,
    merge_narrative_brief_with_state,
)
from game.opening_suggestions import default_opening_suggestions
from game.results import ActionRouteResult, TurnResult
from game.scenario import Scenario
from game.kp_scan_parse import merge_implant_fallback_patch
from game.state_patch import apply_state_patch
from game.turn_context import TurnContext
from game.turn_router import should_run_item_sync, should_run_stat_forge

logger = logging.getLogger(__name__)

ResolveMechanics = Callable[
    [ActionRouteResult, Character, GameState, Scenario], list[str]
]
DeliveredItems = Callable[[ActionRouteResult | None, list[str]], frozenset[str]]


class TurnPipeline:
    """成熟 AI 回合编排：该路由路由，该并发并发，该异步异步。"""

    def __init__(
        self,
        *,
        router: ActionRouter,
        world_state: WorldStateAgent,
        item_sync: ItemSyncAgent,
        stat_forge: StatForgeAgent,
        kp: KPChain,
        memory: LongTermMemoryManager,
        suggester: ActionSuggester,
        window_memory: ConversationWindowMemory,
        resolve_mechanics: ResolveMechanics,
        delivered_item_names: DeliveredItems,
    ):
        self.router = router
        self.world_state = world_state
        self.item_sync = item_sync
        self.stat_forge = stat_forge
        self.kp = kp
        self.memory = memory
        self.suggester = suggester
        self.window_memory = window_memory
        self._resolve_mechanics = resolve_mechanics
        self._delivered_item_names = delivered_item_names

    async def prepare(self, ctx: TurnContext) -> bool:
        """阶段 1–2：行动路由（async）+ 机械结算（sync）。"""
        ctx.enriched_input = apply_guidance_hint(
            ctx.user_input,
            ctx.game_state.turn_count,
            ctx.game_config,
        )
        ctx.route = await self.router.aevaluate(
            ctx.enriched_input,
            ctx.character,
            ctx.game_state,
            ctx.scenario,
            ctx.windowed_history or ctx.history,
        )
        if not ctx.route.approved:
            ctx.rejected = True
            ctx.rejection_reason = ctx.route.rejection_reason
            return False
        try:
            ctx.mechanical_events = self._resolve_mechanics(
                ctx.route, ctx.character, ctx.game_state, ctx.scenario
            )
        except ValueError as exc:
            ctx.rejected = True
            ctx.rejection_reason = str(exc)
            ctx.route = ActionRouteResult(approved=False, rejection_reason=str(exc))
            return False
        return True

    async def sync_world_state(self, ctx: TurnContext) -> list[str]:
        """阶段 3：KP 前的世界状态同步（async）。"""
        ctx.world_patch = await self.world_state.apropose(
            ctx.effective_input,
            ctx.character,
            ctx.game_state,
            ctx.mechanical_events,
            ctx.history,
            route=ctx.route,
        )
        delivered = self._delivered_item_names(ctx.route, ctx.mechanical_events)
        ctx.world_state_events = apply_state_patch(
            ctx.world_patch,
            ctx.character,
            ctx.game_state,
            route=ctx.route,
            delivered_items=delivered,
            mechanical_events=ctx.mechanical_events,
            user_input=ctx.effective_input,
            recent_history=format_recent_history(ctx.history),
        )
        ctx.narrative_brief = self._build_narrative_brief(ctx)
        if ctx.increment_turn:
            ctx.game_state.turn_count += 1
        return ctx.world_state_events

    async def narrate(self, ctx: TurnContext) -> str:
        """阶段 4：KP 叙事（async）。"""
        turn = await self.kp.anarrate(
            character=ctx.character,
            game_state=ctx.game_state,
            scenario_context=ctx.scenario.format_for_prompt(),
            world_id=ctx.scenario.world_id,
            user_input=ctx.narrative_brief,
            history=ctx.windowed_history or ctx.history,
            kp_guidance=ctx.game_config.kp_guidance,
        )
        ctx.kp_response = turn.response
        return ctx.kp_response

    async def sync_items(self, ctx: TurnContext) -> list[str]:
        """阶段 5：KP 后的物品/装备同步（async，按路由决定是否调用）。"""
        if not should_run_item_sync(ctx):
            logger.debug("ItemSync 路由跳过：本轮无物品/装备相关变更信号")
            return []

        ctx.item_patch = await self.item_sync.apropose(
            ctx.effective_input,
            ctx.kp_response,
            ctx.character,
            ctx.game_state,
            ctx.mechanical_events,
            ctx.history,
            route=ctx.route,
        )
        ctx.item_patch = merge_implant_fallback_patch(
            ctx.item_patch,
            ctx.character,
            ctx.kp_response,
            ctx.effective_input,
        )
        delivered = self._delivered_item_names(ctx.route, ctx.mechanical_events)
        ctx.item_sync_events = apply_state_patch(
            ctx.item_patch,
            ctx.character,
            ctx.game_state,
            route=ctx.route,
            delivered_items=delivered,
            mechanical_events=ctx.mechanical_events,
            user_input=ctx.effective_input,
            apply_time=False,
            inventory_sync=True,
        )
        return ctx.item_sync_events

    async def define_entities(self, ctx: TurnContext) -> list[str]:
        """阶段 5b：为缺少 effects 的物品/技能补全战斗数值。"""
        if not should_run_stat_forge(ctx):
            return []

        from game.stat_forge import collect_forge_targets

        targets = collect_forge_targets(ctx.character)
        if not targets:
            return []

        ctx.stat_forge_events = await self.stat_forge.aforge(
            ctx.character,
            ctx.scenario,
            targets,
        )
        return ctx.stat_forge_events

    async def finalize(self, ctx: TurnContext, response: str) -> TurnResult:
        """阶段 6：记忆整理与行动建议（async 并发）。"""
        turn = TurnResult(response=response.strip(), tool_events=ctx.all_tool_events)
        summary_before = ctx.game_state.story_summary

        async def _memory() -> None:
            await self.memory.process_after_turn_async(ctx.game_state, ctx.history)

        suggestions, _ = await gather_best_effort(
            self.suggest_actions(ctx, turn),
            _memory(),
        )
        if suggestions:
            turn.action_suggestions = suggestions
        if ctx.game_state.story_summary != summary_before:
            turn.summary_updated = True
        return turn

    async def run_turn(self, ctx: TurnContext) -> TurnResult:
        """非流式完整回合。"""
        if not await self.prepare(ctx):
            return TurnResult(
                response="",
                rejected=True,
                rejection_reason=ctx.rejection_reason,
            )
        await self.sync_world_state(ctx)
        await self.narrate(ctx)
        await self.sync_items(ctx)
        await self.define_entities(ctx)
        return await self.finalize(ctx, ctx.kp_response)

    def build_narrative_brief_for_stream(self, ctx: TurnContext) -> str:
        """流式路径：在 KP 流开始前构建叙事简报（需先 sync_world_state）。"""
        return ctx.narrative_brief or self._build_narrative_brief(ctx)

    def _build_narrative_brief(self, ctx: TurnContext) -> str:
        brief_static = build_narrative_brief_static(
            ctx.effective_input, ctx.route, ctx.mechanical_events
        )
        return merge_narrative_brief_with_state(
            brief_static,
            ctx.character,
            ctx.game_state,
            ctx.world_state_events,
        )

    async def suggest_actions(self, ctx: TurnContext, turn: TurnResult) -> list[str]:
        settings = get_settings()
        if not settings.enable_action_suggestions or not turn.response or turn.rejected:
            return []
        combat = ctx.game_state.combat
        suggestions = await self.suggester.asuggest(
            ctx.game_state.current_scene,
            turn.response,
            turn_count=ctx.game_state.turn_count,
            in_combat=ctx.game_state.is_in_combat(),
            enemy_names=combat.living_enemy_names() if combat else [],
        )
        if not suggestions and ctx.game_state.turn_count == 0:
            return default_opening_suggestions(ctx.scenario, ctx.game_state)
        return suggestions
