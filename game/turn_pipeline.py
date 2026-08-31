"""回合流水线：KP 前校验 → KP 叙事 → KP 后结算。

三阶段原则
----------
1. **KP 前 · 校验**：Router 批准/驳回 + 买得起/有物品/动作额度；须先出结果的掷骰与战斗机械。
2. **KP · 叙事**：纯文字；简报含玩家原话与已发生的机械结果。
3. **KP 后 · 结算**：post_kp_mechanics（代码）→ Settlement Router → 专职 Sync Agent → StatForge。
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from chain.action_router import ActionRouter
from chain.agent_context import format_recent_history
from chain.async_utils import gather_best_effort
from chain.inventory_sync_agent import InventorySyncAgent
from chain.kp_chain import KPChain
from chain.memory import ConversationWindowMemory
from chain.memory_manager import LongTermMemoryManager
from chain.settlement_router import SettlementRouterAgent
from chain.skill_sync_agent import SkillSyncAgent
from chain.stat_forge_agent import StatForgeAgent
from chain.scene_map_agent import SceneMapAgent
from chain.suggestions import ActionSuggester
from chain.time_sync_agent import TimeSyncAgent
from chain.world_sync_agent import WorldSyncAgent
from config.settings import get_settings
from game.game_config import apply_guidance_hint
from game.models import Character, GameState
from game.narrative_brief import (
    build_narrative_brief_static,
    merge_narrative_brief_with_state,
)
from game.results import ActionRouteResult, TurnResult
from game.scenario import Scenario
from game.state_patch import apply_state_patch
from game.turn_context import TurnContext
from game.turn_router import (
    format_settlement_plan_event,
    resolve_settlement_plan,
    run_post_kp_mechanical_if_needed,
    should_run_stat_forge,
)

logger = logging.getLogger(__name__)

ResolveMechanics = Callable[
    [ActionRouteResult, Character, GameState, Scenario | None, str], list[str]
]
DeliveredItems = Callable[[ActionRouteResult | None, list[str]], frozenset[str]]


class TurnPipeline:
    """回合编排：校验 → 叙事 → 结算。"""

    def __init__(
        self,
        *,
        router: ActionRouter,
        settlement_router: SettlementRouterAgent,
        inventory_sync: InventorySyncAgent,
        skill_sync: SkillSyncAgent,
        time_sync: TimeSyncAgent,
        world_sync: WorldSyncAgent,
        stat_forge: StatForgeAgent,
        kp: KPChain,
        memory: LongTermMemoryManager,
        suggester: ActionSuggester,
        window_memory: ConversationWindowMemory,
        scene_map: SceneMapAgent | None = None,
        resolve_mechanics: ResolveMechanics,
        delivered_item_names: DeliveredItems,
    ):
        self.router = router
        self.settlement_router = settlement_router
        self.inventory_sync = inventory_sync
        self.skill_sync = skill_sync
        self.time_sync = time_sync
        self.world_sync = world_sync
        self.stat_forge = stat_forge
        self.kp = kp
        self.memory = memory
        self.suggester = suggester
        self.window_memory = window_memory
        self.scene_map = scene_map if scene_map is not None else SceneMapAgent()
        self._resolve_mechanics = resolve_mechanics
        self._delivered_item_names = delivered_item_names

    async def prepare(self, ctx: TurnContext) -> bool:
        """KP 前 · 校验：路由 + 须先于叙事的机械结果（检定/战斗/动作额度）。"""
        ctx.enriched_input = apply_guidance_hint(
            ctx.user_input,
            ctx.game_state.turn_count,
            ctx.game_config,
            scenario=ctx.scenario,
            progress=ctx.game_state.scenario_progress,
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
                ctx.route,
                ctx.character,
                ctx.game_state,
                ctx.scenario,
                ctx.effective_input,
            )
        except ValueError as exc:
            ctx.rejected = True
            ctx.rejection_reason = str(exc)
            ctx.route = ActionRouteResult(approved=False, rejection_reason=str(exc))
            return False
        return True

    async def build_narrative_brief(self, ctx: TurnContext) -> str:
        """KP 前 · 组装叙事简报（无 WorldState LLM）。"""
        from game.scene_map import sync_map_to_current_scene

        ctx.map_travel_from = ctx.game_state.map_travel_from.strip()
        sync_map_to_current_scene(ctx.game_state, ctx.scenario)
        ctx.narrative_brief = self._build_narrative_brief(ctx)
        if ctx.increment_turn:
            ctx.game_state.turn_count += 1
        return ctx.narrative_brief

    async def narrate(self, ctx: TurnContext) -> str:
        """KP · 叙事。"""
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

    async def settle_after_kp(self, ctx: TurnContext) -> list[str]:
        """KP 后 · 统一结算编排（Sync Agent 并发 propose、串行 apply）。"""
        if ctx.rejected or not ctx.kp_response.strip():
            return []

        events: list[str] = []
        delivered = self._delivered_item_names(ctx.route, ctx.settlement_events)
        record_turn = ctx.game_state.turn_count

        ctx.post_kp_events = run_post_kp_mechanical_if_needed(
            ctx.route,
            ctx.character,
            ctx.game_state,
            ctx.mechanical_events,
        )
        events.extend(ctx.post_kp_events)
        delivered = self._delivered_item_names(ctx.route, ctx.settlement_events)

        if ctx.is_opening:
            ctx.settlement_plan = resolve_settlement_plan(ctx)
        else:
            router_plan = await self.settlement_router.aplan(
                ctx.effective_input,
                ctx.kp_response,
                ctx.character,
                ctx.game_state,
                ctx.settlement_events,
                route=ctx.route,
            )
            ctx.settlement_plan = resolve_settlement_plan(ctx, router_plan=router_plan)

        plan = ctx.settlement_plan
        assert plan is not None
        events.append(format_settlement_plan_event(plan))

        patch_kwargs = dict(
            route=ctx.route,
            delivered_items=delivered,
            mechanical_events=ctx.settlement_events,
            user_input=ctx.effective_input,
            recent_history=format_recent_history(ctx.history),
            scene_record_turn=record_turn,
        )

        propose_labels: list[str] = []
        propose_coros = []
        if plan.inventory_sync:
            propose_labels.append("inventory")
            propose_coros.append(
                self.inventory_sync.apropose(
                    ctx.effective_input,
                    ctx.kp_response,
                    ctx.character,
                    ctx.game_state,
                    ctx.settlement_events,
                    ctx.history,
                    route=ctx.route,
                )
            )
        if plan.skill_sync:
            propose_labels.append("skill")
            propose_coros.append(
                self.skill_sync.apropose(
                    ctx.effective_input,
                    ctx.kp_response,
                    ctx.character,
                    ctx.game_state,
                    ctx.settlement_events,
                    route=ctx.route,
                )
            )
        if plan.time_sync:
            propose_labels.append("time")
            propose_coros.append(
                self.time_sync.apropose(
                    ctx.effective_input,
                    ctx.kp_response,
                    ctx.character,
                    ctx.game_state,
                    ctx.settlement_events,
                    route=ctx.route,
                )
            )
        if plan.world_sync:
            propose_labels.append("world")
            propose_coros.append(
                self.world_sync.apropose(
                    ctx.effective_input,
                    ctx.kp_response,
                    ctx.character,
                    ctx.game_state,
                    ctx.settlement_events,
                    ctx.history,
                    route=ctx.route,
                )
            )

        proposed = await gather_best_effort(*propose_coros) if propose_coros else []
        patches = dict(zip(propose_labels, proposed))

        if plan.inventory_sync:
            patch = patches.get("inventory")
            if patch is not None:
                ctx.inventory_patch = patch
                ctx.inventory_sync_events = apply_state_patch(
                    ctx.inventory_patch,
                    ctx.character,
                    ctx.game_state,
                    apply_time=False,
                    inventory_sync=True,
                    **patch_kwargs,
                )
                events.extend(ctx.inventory_sync_events)

        if plan.skill_sync:
            patch = patches.get("skill")
            if patch is not None:
                ctx.skill_patch = patch
                ctx.skill_sync_events = apply_state_patch(
                    ctx.skill_patch,
                    ctx.character,
                    ctx.game_state,
                    apply_time=False,
                    **patch_kwargs,
                )
                events.extend(ctx.skill_sync_events)

        if plan.time_sync:
            patch = patches.get("time")
            if patch is not None:
                ctx.time_patch = patch
                ctx.time_sync_events = apply_state_patch(
                    ctx.time_patch,
                    ctx.character,
                    ctx.game_state,
                    apply_time=True,
                    inventory_sync=False,
                    **patch_kwargs,
                )
                events.extend(ctx.time_sync_events)
                from game.narrative_time import reconcile_clock_from_kp_narrative

                extra_elapsed = (
                    ctx.time_patch.time.advance_minutes
                    if ctx.time_patch.time is not None
                    else 0
                )
                events.extend(
                    reconcile_clock_from_kp_narrative(
                        ctx.game_state,
                        ctx.kp_response,
                        extra_elapsed=extra_elapsed,
                    )
                )

        if plan.world_sync:
            patch = patches.get("world")
            if patch is not None:
                ctx.world_patch = patch
                ctx.world_sync_events = apply_state_patch(
                    ctx.world_patch,
                    ctx.character,
                    ctx.game_state,
                    apply_time=False,
                    inventory_sync=False,
                    **patch_kwargs,
                )
                events.extend(ctx.world_sync_events)
                ctx.map_needs_update = _should_refresh_scene_map(ctx)
                if not ctx.map_needs_update:
                    ctx.game_state.map_travel_from = ""

        from game.scenario_progress import update_scenario_progress_after_turn

        events.extend(
            update_scenario_progress_after_turn(
                ctx.game_state,
                ctx.scenario,
                kp_text=ctx.kp_response,
                state_events=events,
            )
        )

        return events

    async def define_entities(self, ctx: TurnContext) -> list[str]:
        """为缺少 effects 的物品/技能补全战斗数值。"""
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
        """记忆整理与行动建议（async 并发）。"""
        turn = TurnResult(response=response.strip(), tool_events=ctx.all_tool_events)
        summary_before = ctx.game_state.story_summary

        async def _memory() -> None:
            await self.memory.process_after_turn_async(ctx.game_state, ctx.history)

        async def _scene_map() -> None:
            if ctx.map_needs_update:
                await self.scene_map.aupdate(
                    ctx.game_state,
                    ctx.scenario,
                    ctx.history,
                    travel_from=ctx.map_travel_from,
                )
                ctx.game_state.map_travel_from = ""

        suggestions, _, _ = await gather_best_effort(
            self.suggest_actions(ctx, turn),
            _memory(),
            _scene_map(),
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
        await self.build_narrative_brief(ctx)
        await self.narrate(ctx)
        await self.settle_after_kp(ctx)
        await self.define_entities(ctx)
        return await self.finalize(ctx, ctx.kp_response)

    def build_narrative_brief_for_stream(self, ctx: TurnContext) -> str:
        """流式路径：在 KP 流开始前构建叙事简报。"""
        return ctx.narrative_brief or self._build_narrative_brief(ctx)

    def _build_narrative_brief(self, ctx: TurnContext) -> str:
        from game.scenario_progress import ensure_scenario_progress

        progress = (
            ensure_scenario_progress(ctx.game_state)
            if ctx.scenario.key_nodes
            else None
        )
        brief_static = build_narrative_brief_static(
            ctx.effective_input,
            ctx.route,
            ctx.mechanical_events,
            game_config=ctx.game_config,
            scenario=ctx.scenario,
            progress=progress,
            turn_count=ctx.game_state.turn_count,
        )
        return merge_narrative_brief_with_state(
            brief_static,
            ctx.character,
            ctx.game_state,
            None,
            history=ctx.history,
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
        return suggestions


def _should_refresh_scene_map(ctx: TurnContext) -> bool:
    """换场景或获得地图时调用 Map Agent 增量维护节点与连边。"""
    if ctx.world_patch.map_discovery:
        return True
    if ctx.is_opening:
        return False
    scene = ctx.world_patch.scene
    return scene is not None and bool(scene.scene_id.strip())
