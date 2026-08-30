from chain.action_router import ActionRouter
from chain.async_utils import gather_best_effort, run_async
from chain.inventory_sync_agent import InventorySyncAgent
from chain.opening_integrator import OpeningIntegrator
from chain.kp_chain import KPChain
from chain.kp_meta_agent import KpMetaAgent, KpMetaResult
from chain.memory import ConversationWindowMemory
from chain.memory_manager import LongTermMemoryManager
from chain.settlement_router import SettlementRouterAgent
from chain.skill_sync_agent import SkillSyncAgent
from chain.suggestions import ActionSuggester
from chain.scene_map_agent import SceneMapAgent
from chain.stat_forge_agent import StatForgeAgent
from chain.summarizer import StorySummarizer
from chain.time_sync_agent import TimeSyncAgent
from chain.world_sync_agent import WorldSyncAgent
from config.settings import get_settings
from game.adventure_snapshot import restore_adventure, snapshot_adventure
from game.combat import (
    advance_after_player_action,
    end_player_turn,
    maybe_end_combat,
    player_attack,
    player_move,
    resolve_dash,
    resolve_defend,
    resolve_flee,
    resolve_grapple,
    resolve_help,
    resolve_interact,
    resolve_search_in_combat,
    resolve_shove,
    resolve_talk,
    resolve_pickup_in_combat,
    resolve_until_player_turn,
    resolve_use_item_in_combat,
    start_combat,
)
from game.dice import roll
from game.post_kp_mechanics import delivered_item_names
from game.game_config import GameConfig, apply_guidance_hint, default_game_config
from game.kp_sanitize import sanitize_kp_narrative
from game.models import Character, ChatMessage, GameState
from game.opening_brief import OpeningBrief
from game.results import ActionRouteResult, TurnResult
from game.kp_directive import is_kp_directive, parse_kp_directive
from game.narrative_time import apply_time_patch
from game.results import TimePatch
from game.state_patch import apply_state_patch
from game.turn_context import TurnContext
from game.turn_pipeline import TurnPipeline
from game.check_consequences import apply_check_failure_consequences
from game.rules import ability_check, format_check_for_kp
from game.skill_check import skill_bonus_for_route
from game.scenario import Scenario

START_GAME_INSTRUCTION = """\
游戏刚刚开始。请根据下方【模组信息】做开场，并全程担任引导型 KP。

开场叙事必须包含（**融入故事**，有画面、有气氛，不要列清单、不要出戏）：
1. 场景：你在哪里——用可见/可闻/可触的细节让人「身临其境」；
2. 处境：刚发生了什么，你为什么在这里；
3. 目标：当前最重要的一件事是什么（与 initial_quests 一致）；
4. 引导：用 1–2 句**自然融入剧情**的方向暗示（调查、交谈、移动等），不要替玩家做决定，不要菜单式列举。

工具：开场场景/NPC/任务由系统自动同步；你只需写开场叙事。
结尾留明确的行动入口，让玩家知道第一句话该说什么。

若输入含【长期角色履历】：这是老角色进入新模组。尊重其过往战役、技能与背包；开场可自然提及来历，但剧情仍从新模组 initial_quests 起步，不要复述全部履历。

若输入含【开场入场逻辑】：必须严格遵循，使玩家背景与模组开场一致；不得写成与背景矛盾的身份；遵守「NPC 尚不应知道」列表。

信息分层：只写 NPC 合理应知的信息。匿名代号、暗网投递、隐藏身份等，在玩家未暴露前，NPC 不得确知。禁止让 NPC 凭空指认「压缩包就是你发的」。

不要在开场末尾重复第二遍行动建议或写「开场已就绪」「你可以试着…」等系统腔二次总结。

若含【长期角色履历】：玩家虽是老角色，但对**本模组**仍是第一次。开场结尾**仍须**用 1–2 句融入叙事的方式，给出**本场景**下可尝试的具体方向（调查什么、和谁交谈、检查什么），让玩家知道第一句话说什么；不要只写履历、氛围或任务概述就收笔。"""

_OPENING_CONSISTENCY_RULE = (
    "【一致性硬性要求】开场叙事必须遵循上方【开场入场逻辑】。"
    "禁止出现与玩家背景矛盾的身份或经历（除非入场逻辑已明确伪装、隐姓埋名、职务视察或委托关系，且开篇点明）。"
    "严格遵守「NPC 此时还不应知道」：匿名投递者身份在未暴露前，NPC 不能确指玩家就是发信人。"
)


def _build_start_instruction(
    character: Character,
    scenario: Scenario,
    career_context: str = "",
    integrator: OpeningIntegrator | None = None,
    brief: OpeningBrief | None = None,
    game_config: GameConfig | None = None,
) -> str:
    if brief is None:
        brief = (integrator or OpeningIntegrator()).generate(character, scenario)
    lines: list[str] = []
    if career_context.strip():
        lines.append(career_context.strip())
        lines.append(
            "【开场上屏提示】长期角色进入新模组：KP 开场仍须给出本场景的具体行动入口（见上方 START 要求第 4 点），"
            "不要假设玩家已知道该做什么。"
        )
    lines.append(brief.format_for_kp())
    lines.append(START_GAME_INSTRUCTION)
    config = game_config or default_game_config()
    if config.kp_guidance == "script_guided":
        lines.append(
            "【按剧本推进】本局为剧本引导模式：开场须自然引出 initial_quests，"
            "并在叙事中铺设第一个 key_node 的入口线索；仍禁止抢戏。"
        )
    elif config.kp_guidance == "freeform":
        lines.append(
            "【自由即兴】本局为自由模式：尊重玩家背景与当前情境即可，"
            "不必主动往 key_nodes 推；开场结尾可省略方向提示。"
        )
    lines.append(_OPENING_CONSISTENCY_RULE)
    return "\n\n".join(lines)


class GameOrchestrator:
    def __init__(
        self,
        kp_chain: KPChain | None = None,
        summarizer: StorySummarizer | None = None,
        suggester: ActionSuggester | None = None,
        memory_manager: LongTermMemoryManager | None = None,
        action_router: ActionRouter | None = None,
        opening_integrator: OpeningIntegrator | None = None,
        settlement_router: SettlementRouterAgent | None = None,
        inventory_sync_agent: InventorySyncAgent | None = None,
        skill_sync_agent: SkillSyncAgent | None = None,
        time_sync_agent: TimeSyncAgent | None = None,
        world_sync_agent: WorldSyncAgent | None = None,
        stat_forge_agent: StatForgeAgent | None = None,
        scene_map_agent: SceneMapAgent | None = None,
        kp_meta_agent: KpMetaAgent | None = None,
    ):
        self.kp = kp_chain if kp_chain is not None else KPChain()
        self.kp_meta = kp_meta_agent if kp_meta_agent is not None else KpMetaAgent()
        self.summarizer = summarizer if summarizer is not None else StorySummarizer()
        self.suggester = suggester if suggester is not None else ActionSuggester()
        self.memory = LongTermMemoryManager(self.summarizer) if memory_manager is None else memory_manager
        self.router = action_router if action_router is not None else ActionRouter()
        self.settlement_router = (
            settlement_router if settlement_router is not None else SettlementRouterAgent()
        )
        self.inventory_sync = (
            inventory_sync_agent if inventory_sync_agent is not None else InventorySyncAgent()
        )
        self.skill_sync = skill_sync_agent if skill_sync_agent is not None else SkillSyncAgent()
        self.time_sync = time_sync_agent if time_sync_agent is not None else TimeSyncAgent()
        self.world_sync = world_sync_agent if world_sync_agent is not None else WorldSyncAgent()
        self.stat_forge = stat_forge_agent if stat_forge_agent is not None else StatForgeAgent()
        self.scene_map = scene_map_agent if scene_map_agent is not None else SceneMapAgent()
        self.opening_integrator = (
            opening_integrator if opening_integrator is not None else OpeningIntegrator()
        )
        settings = get_settings()
        self.window_memory = ConversationWindowMemory(window_size=settings.max_history_messages)
        self.pipeline = TurnPipeline(
            router=self.router,
            settlement_router=self.settlement_router,
            inventory_sync=self.inventory_sync,
            skill_sync=self.skill_sync,
            time_sync=self.time_sync,
            world_sync=self.world_sync,
            stat_forge=self.stat_forge,
            kp=self.kp,
            memory=self.memory,
            suggester=self.suggester,
            window_memory=self.window_memory,
            scene_map=self.scene_map,
            resolve_mechanics=self._resolve_mechanics,
            delivered_item_names=delivered_item_names,
        )

    def start_game(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        *,
        career_context: str = "",
        game_config: GameConfig | None = None,
    ) -> TurnResult:
        return run_async(
            self.astart_game(
                character,
                game_state,
                scenario,
                career_context=career_context,
                game_config=game_config,
            )
        )

    async def astart_game(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        *,
        career_context: str = "",
        game_config: GameConfig | None = None,
    ) -> TurnResult:
        config = game_config or default_game_config()
        scenario.apply_to_game_state(game_state)
        game_state.started = True
        brief = self.opening_integrator.generate(character, scenario)
        user_input = _build_start_instruction(
            character,
            scenario,
            career_context,
            self.opening_integrator,
            brief=brief,
            game_config=config,
        )
        turn = await self._run_turn_via_pipeline(
            character=character,
            game_state=game_state,
            scenario=scenario,
            user_input=user_input,
            history=[],
            increment_turn=False,
            is_opening=True,
            game_config=config,
        )
        return turn

    def start_game_stream(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        *,
        career_context: str = "",
        game_config: GameConfig | None = None,
    ):
        config = game_config or default_game_config()
        scenario.apply_to_game_state(game_state)
        game_state.started = True
        brief = self.opening_integrator.generate(character, scenario)
        user_input = _build_start_instruction(
            character,
            scenario,
            career_context,
            self.opening_integrator,
            brief=brief,
            game_config=config,
        )
        char_snap, state_snap = snapshot_adventure(character, game_state)
        ctx = TurnContext(
            user_input=user_input,
            character=character,
            game_state=game_state,
            scenario=scenario,
            history=[],
            windowed_history=[],
            increment_turn=False,
            is_opening=True,
            enriched_input=user_input,
            mechanical_events=[],
            game_config=config,
        )
        rejection, pre_events, run_state, stream, item_sync, mem, finish = (
            self._stream_turn_phased(ctx)
        )

        def rollback_turn() -> None:
            restore_adventure(character, game_state, char_snap, state_snap)

        def finish_with_opening(response: str) -> TurnResult:
            return finish(response)

        return rejection, pre_events, run_state, stream, item_sync, mem, finish_with_opening, rollback_turn

    def player_turn(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        user_input: str,
        history: list[ChatMessage],
        *,
        game_config: GameConfig | None = None,
    ) -> TurnResult:
        return run_async(
            self.aplayer_turn(
                character,
                game_state,
                scenario,
                user_input,
                history,
                game_config=game_config,
            )
        )

    async def aplayer_turn(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        user_input: str,
        history: list[ChatMessage],
        *,
        game_config: GameConfig | None = None,
    ) -> TurnResult:
        if is_kp_directive(user_input):
            windowed = self.window_memory.get_history(history)
            return await self._akp_meta_turn(
                character, game_state, scenario, user_input, history, windowed
            )
        windowed = self.window_memory.get_history(history)
        char_snap, state_snap = snapshot_adventure(character, game_state)
        try:
            return await self._run_turn_via_pipeline(
                character=character,
                game_state=game_state,
                scenario=scenario,
                user_input=user_input,
                history=history,
                windowed_history=windowed,
                game_config=game_config,
            )
        except Exception:
            restore_adventure(character, game_state, char_snap, state_snap)
            raise

    async def _akp_meta_turn(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        user_input: str,
        history: list[ChatMessage],
        windowed_history: list[ChatMessage],
    ) -> TurnResult:
        meta_message = parse_kp_directive(user_input)
        if meta_message is None:
            meta_message = ""
        if not meta_message.strip():
            return TurnResult(
                response="**【KP 沟通】**\n\n请在 【kp】 后面写上你想沟通的内容。",
                tool_events=[],
            )
        result = await self.kp_meta.arespond(
            meta_message, character, game_state, windowed_history or history
        )
        events, response = self._apply_kp_meta_result(result, character, game_state)
        events.extend(await self._forge_pending_entities_async(character, scenario))
        return TurnResult(response=response, tool_events=events)

    def _apply_kp_meta_result(
        self,
        result: KpMetaResult,
        character: Character,
        game_state: GameState,
    ) -> tuple[list[str], str]:
        events = apply_state_patch(
            result.patch,
            character,
            game_state,
            apply_time=False,
            user_input="",
        )
        time_patch = result.patch.time
        if time_patch is not None and (
            time_patch.cancel_deadline_ids or time_patch.enforce_deadline_ids
        ):
            events.extend(
                apply_time_patch(
                    game_state,
                    TimePatch(
                        cancel_deadline_ids=list(time_patch.cancel_deadline_ids),
                        enforce_deadline_ids=list(time_patch.enforce_deadline_ids),
                    ),
                    character,
                )
            )
        if result.character_hp is not None:
            before = character.hp
            character.hp = max(0, min(int(result.character_hp), character.max_hp))
            if character.hp != before:
                events.append(
                    f"💚 KP 修正：HP {before} → {character.hp}/{character.max_hp}"
                )
        if result.patch.reroll is not None:
            from game.check_reroll import apply_reroll_patch

            events.extend(
                apply_reroll_patch(result.patch.reroll, character, game_state)
            )
        response = self._format_kp_meta_response(result.response)
        return events, response

    async def _forge_pending_entities_async(
        self,
        character: Character,
        scenario: Scenario,
    ) -> list[str]:
        from game.stat_forge import collect_forge_targets

        targets = collect_forge_targets(character)
        if not targets:
            return []
        return await self.stat_forge.aforge(character, scenario, targets)

    def _forge_pending_entities_sync(
        self,
        character: Character,
        scenario: Scenario,
    ) -> list[str]:
        from chain.async_utils import run_async

        return run_async(self._forge_pending_entities_async(character, scenario))

    @staticmethod
    def _format_kp_meta_response(text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return "**【KP 沟通】**\n\n收到。"
        if cleaned.startswith("**【KP") or cleaned.startswith("【KP"):
            return cleaned
        return f"**【KP 沟通】**\n\n{cleaned}"

    async def _run_turn_via_pipeline(
        self,
        *,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        user_input: str,
        history: list[ChatMessage],
        windowed_history: list[ChatMessage] | None = None,
        increment_turn: bool = True,
        is_opening: bool = False,
        prebuilt_ctx: TurnContext | None = None,
        game_config: GameConfig | None = None,
    ) -> TurnResult:
        config = game_config or default_game_config()
        ctx = prebuilt_ctx or TurnContext(
            user_input=user_input,
            character=character,
            game_state=game_state,
            scenario=scenario,
            history=history,
            windowed_history=windowed_history or history,
            increment_turn=increment_turn,
            is_opening=is_opening,
            game_config=config,
        )
        if is_opening:
            ctx.route = None
            ctx.enriched_input = user_input
            ctx.mechanical_events = []
            await self.pipeline.build_narrative_brief(ctx)
            await self.pipeline.narrate(ctx)
            await self.pipeline.settle_after_kp(ctx)
            await self.pipeline.define_entities(ctx)
            return await self.pipeline.finalize(ctx, ctx.kp_response)
        return await self.pipeline.run_turn(ctx)

    def player_turn_stream(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        user_input: str,
        history: list[ChatMessage],
        *,
        game_config: GameConfig | None = None,
    ):
        if is_kp_directive(user_input):
            return self._stream_kp_meta_turn(
                character, game_state, scenario, user_input, history
            )
        config = game_config or default_game_config()
        windowed = self.window_memory.get_history(history)
        char_snap, state_snap = snapshot_adventure(character, game_state)
        ctx = TurnContext(
            user_input=user_input,
            character=character,
            game_state=game_state,
            scenario=scenario,
            history=history,
            windowed_history=windowed,
            increment_turn=True,
            game_config=config,
        )
        if not run_async(self.pipeline.prepare(ctx)):
            rejected_turn = TurnResult(
                response="",
                rejected=True,
                rejection_reason=ctx.rejection_reason,
            )

            def finish_rejected(_response: str) -> TurnResult:
                return rejected_turn

            def run_state_phase_rejected() -> list[str]:
                return []

            def run_item_sync_phase_rejected() -> list[str]:
                return []

            def run_memory_finalize_rejected() -> bool:
                return False

            return (
                rejected_turn,
                ctx.mechanical_events,
                run_state_phase_rejected,
                iter([]),
                run_item_sync_phase_rejected,
                run_memory_finalize_rejected,
                finish_rejected,
                lambda: restore_adventure(character, game_state, char_snap, state_snap),
            )

        rejection, pre_events, run_state, stream, item_sync, mem, finish = (
            self._stream_turn_phased(ctx)
        )

        def rollback_turn() -> None:
            restore_adventure(character, game_state, char_snap, state_snap)

        return rejection, pre_events, run_state, stream, item_sync, mem, finish, rollback_turn

    def auto_combat_turn_stream(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
        *,
        game_config: GameConfig | None = None,
    ):
        from game.auto_combat import format_auto_combat_user_input, run_auto_combat

        char_snap, state_snap = snapshot_adventure(character, game_state)
        if not game_state.is_in_combat():
            rejected = TurnResult(
                response="",
                rejected=True,
                rejection_reason="当前不在战斗中，无法自动战斗。",
            )

            def finish_rejected(_response: str) -> TurnResult:
                return rejected

            return (
                rejected,
                [],
                lambda: [],
                iter([]),
                lambda _kp: [],
                lambda: False,
                finish_rejected,
                lambda: None,
            )

        auto_result = run_auto_combat(character, game_state)
        config = game_config or default_game_config()
        user_input = format_auto_combat_user_input(auto_result)
        windowed = self.window_memory.get_history(history)
        ctx = TurnContext(
            user_input=user_input,
            character=character,
            game_state=game_state,
            scenario=scenario,
            history=history,
            windowed_history=windowed,
            increment_turn=True,
            game_config=config,
        )
        ctx.route = ActionRouteResult(approved=True, mode="exploration", combat_action="none")
        ctx.enriched_input = user_input
        ctx.mechanical_events = list(auto_result.events)

        rejection, pre_events, run_state, stream, item_sync, mem, finish = (
            self._stream_turn_phased(ctx)
        )

        def rollback_turn() -> None:
            restore_adventure(character, game_state, char_snap, state_snap)

        return rejection, pre_events, run_state, stream, item_sync, mem, finish, rollback_turn

    def auto_combat_turn(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
        *,
        game_config: GameConfig | None = None,
    ) -> TurnResult:
        return run_async(
            self.aauto_combat_turn(
                character,
                game_state,
                scenario,
                history,
                game_config=game_config,
            )
        )

    async def aauto_combat_turn(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
        *,
        game_config: GameConfig | None = None,
    ) -> TurnResult:
        config = game_config or default_game_config()
        windowed = self.window_memory.get_history(history)
        (
            rejection,
            pre_events,
            run_state,
            stream,
            item_sync,
            mem,
            finish,
            rollback,
        ) = self.auto_combat_turn_stream(
            character, game_state, scenario, history, game_config=config
        )
        if rejection is not None and rejection.rejected:
            return rejection
        run_state()
        response = "".join(stream)
        item_sync(response)
        mem()
        return finish(response)

    def _stream_kp_meta_turn(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        user_input: str,
        history: list[ChatMessage],
    ):
        windowed = self.window_memory.get_history(history)
        meta_message = parse_kp_directive(user_input)
        if meta_message is None:
            meta_message = ""
        char_snap, state_snap = snapshot_adventure(character, game_state)
        holder: dict[str, object] = {"events": [], "response": ""}

        def run_state_phase() -> list[str]:
            if not meta_message.strip():
                response = self._format_kp_meta_response("请在 【kp】 后面写上你想沟通的内容。")
                holder["response"] = response
                return []
            result = run_async(
                self.kp_meta.arespond(
                    meta_message, character, game_state, windowed or history
                )
            )
            events, response = self._apply_kp_meta_result(result, character, game_state)
            events.extend(self._forge_pending_entities_sync(character, scenario))
            holder["events"] = events
            holder["response"] = response
            return events

        def text_stream():
            response = str(holder.get("response") or "")
            if response:
                yield response

        def run_item_sync_phase(_kp_response: str) -> list[str]:
            return []

        def run_memory_finalize() -> bool:
            return False

        def finish(_response: str) -> TurnResult:
            response = str(holder.get("response") or _response).strip()
            return TurnResult(
                response=response or self._format_kp_meta_response("收到。"),
                tool_events=list(holder.get("events") or []),
            )

        def rollback_turn() -> None:
            restore_adventure(character, game_state, char_snap, state_snap)

        return (
            None,
            [],
            run_state_phase,
            text_stream(),
            run_item_sync_phase,
            run_memory_finalize,
            finish,
            rollback_turn,
        )

    def _stream_turn_phased(
        self,
        ctx: TurnContext,
    ):
        """分阶段流式回合：机械 → 叙事简报 → KP 流 → KP 后结算 → 异步收尾。"""
        tool_events = list(ctx.mechanical_events)
        state_result: dict[str, object] = {}

        def run_state_phase() -> list[str]:
            run_async(self.pipeline.build_narrative_brief(ctx))
            state_result["brief"] = ctx.narrative_brief
            return []

        def text_stream():
            brief = state_result.get("brief")
            if brief is None:
                raise RuntimeError("run_state_phase must be called before consuming text_stream")
            yield from self.kp.narrate_stream(
                character=ctx.character,
                game_state=ctx.game_state,
                scenario_context=ctx.scenario.format_for_prompt(),
                world_id=ctx.scenario.world_id,
                user_input=str(brief),
                history=ctx.windowed_history or ctx.history,
                kp_guidance=ctx.game_config.kp_guidance,
            )

        def run_item_sync_phase(kp_response: str) -> list[str]:
            ctx.kp_response = sanitize_kp_narrative(kp_response.strip())
            settle_events = run_async(self.pipeline.settle_after_kp(ctx))
            tool_events.extend(settle_events)
            forge_events = run_async(self.pipeline.define_entities(ctx))
            tool_events.extend(forge_events)
            return settle_events + forge_events

        def run_memory_finalize() -> bool:
            summary_before = ctx.game_state.story_summary
            run_async(
                gather_best_effort(
                    self.memory.process_after_turn_async(ctx.game_state, ctx.history),
                    self._refresh_scene_map_if_needed(ctx),
                )
            )
            return ctx.game_state.story_summary != summary_before

        def finish(response: str) -> TurnResult:
            ctx.kp_response = sanitize_kp_narrative(response.strip())
            turn = TurnResult(response=ctx.kp_response, tool_events=tool_events)
            suggestions = run_async(self.pipeline.suggest_actions(ctx, turn))
            if suggestions:
                turn.action_suggestions = suggestions
            return turn

        return None, list(ctx.mechanical_events), run_state_phase, text_stream(), run_item_sync_phase, run_memory_finalize, finish

    async def _aprepare_player_input(
        self,
        user_input: str,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
        windowed: list[ChatMessage],
    ) -> tuple[str, list[str], ActionRouteResult]:
        enriched_input = apply_guidance_hint(
            user_input, game_state.turn_count, default_game_config()
        )
        route = await self.router.aevaluate(
            enriched_input, character, game_state, scenario, windowed or history
        )
        if not route.approved:
            return enriched_input, [], route
        try:
            pre_tool_events = self._resolve_mechanics(
                route, character, game_state, scenario, enriched_input
            )
        except ValueError as exc:
            return enriched_input, [], ActionRouteResult(
                approved=False,
                rejection_reason=str(exc),
            )
        return enriched_input, pre_tool_events, route

    def _prepare_player_input(
        self,
        user_input: str,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
        windowed: list[ChatMessage],
    ) -> tuple[str, list[str], ActionRouteResult]:
        enriched_input = apply_guidance_hint(
            user_input, game_state.turn_count, default_game_config()
        )
        route = self.router.evaluate(
            enriched_input, character, game_state, scenario, windowed or history
        )
        if not route.approved:
            return enriched_input, [], route
        try:
            pre_tool_events = self._resolve_mechanics(
                route, character, game_state, scenario, enriched_input
            )
        except ValueError as exc:
            return enriched_input, [], ActionRouteResult(
                approved=False,
                rejection_reason=str(exc),
            )
        return enriched_input, pre_tool_events, route

    def _resolve_mechanics(
        self,
        route: ActionRouteResult,
        character: Character,
        game_state: GameState,
        scenario: Scenario | None = None,
        user_input: str = "",
    ) -> list[str]:
        pre_tool_events: list[str] = []
        world_id = scenario.world_id if scenario else ""

        if route.trigger_combat:
            pre_tool_events.append(
                start_combat(
                    character,
                    game_state,
                    route.enemies_spec,
                    enemy_defs=route.enemy_defs or None,
                    world_id=world_id,
                )
            )
            pre_tool_events.extend(resolve_until_player_turn(character, game_state))
            combat = game_state.combat
            if combat and combat.active and combat.is_player_turn():
                pre_tool_events.append("轮到你行动。请在本轮发送战斗指令（移动、攻击、防御等）。")

        if game_state.is_in_combat() and route.combat_action != "none" and not route.trigger_combat:
            combat = game_state.combat
            if not combat or not combat.active:
                pass
            elif not combat.is_player_turn():
                actor = combat.current_actor()
                actor_label = character.name if actor == "player" else actor
                action_label = route.combat_action
                if route.trigger_combat:
                    raise ValueError(
                        f"战斗已开始，但当前仍是 {actor_label} 的回合，"
                        f"无法在同一句话里立刻执行「{action_label}」。"
                        "请先等待先攻轮次结束，轮到你时再行动。"
                    )
                raise ValueError(
                    f"还没轮到你，当前是 {actor_label} 的回合，无法执行「{action_label}」。"
                )
            elif route.combat_action == "attack" and not route.attack_target.strip():
                raise ValueError("请明确要攻击的敌人。")
            else:
                combat = game_state.combat
                if combat:
                    from game.combat_targets import normalize_combat_enemy_refs

                    normalize_combat_enemy_refs(route, combat)
                pre_tool_events.extend(
                    self._execute_combat_action(
                        route, character, game_state, user_input=user_input
                    )
                )
                if self._should_advance_combat_after_action(route, game_state):
                    pre_tool_events.extend(
                        advance_after_player_action(character, game_state)
                    )

        elif game_state.is_in_combat() and route.item_usage == "pickup" and not route.trigger_combat:
            pre_tool_events.extend(
                resolve_pickup_in_combat(
                    character, game_state, route.referenced_items
                )
            )
            if self._should_advance_combat_after_action(route, game_state):
                pre_tool_events.extend(
                    advance_after_player_action(character, game_state)
                )

        elif game_state.is_in_combat() and route.item_usage == "use" and not route.trigger_combat:
            from game.combat_item_use import combat_use_item_cost

            if route.combat_action == "use_item" and route.action_cost in (
                "main",
                "bonus",
                "free",
            ):
                cost = route.action_cost
            elif route.referenced_items:
                cost = combat_use_item_cost(character, route.referenced_items[0])
            else:
                cost = "bonus"
            pre_tool_events.extend(
                resolve_use_item_in_combat(
                    character,
                    game_state,
                    route.referenced_items,
                    cost=cost,
                    attack_target=route.attack_target,
                )
            )
            if self._should_advance_combat_after_action(route, game_state):
                pre_tool_events.extend(
                    advance_after_player_action(character, game_state)
                )

        if not game_state.is_in_combat() and route.needs_roll:
            from game.check_reroll import apply_pending_reroll_to_route

            pre_tool_events.extend(
                apply_pending_reroll_to_route(
                    route, game_state, user_input=user_input
                )
            )
            roll_events, roll_success = self._execute_pre_roll(
                route, character, game_state, user_input=user_input
            )
            pre_tool_events.extend(roll_events)

        end_msg, _defeated = maybe_end_combat(game_state, character)
        if end_msg:
            pre_tool_events.append(end_msg)

        return pre_tool_events

    @staticmethod
    def _execute_pre_move(
        route: ActionRouteResult,
        character: Character,
        game_state: GameState,
    ) -> list[str]:
        if route.move_meters <= 0 or not route.move_target.strip():
            return []
        return [
            player_move(
                character,
                game_state,
                route.move_target,
                route.move_meters,
                toward=route.move_toward,
            )
        ]

    @staticmethod
    def _execute_pre_pickup(
        route: ActionRouteResult,
        character: Character,
        game_state: GameState,
    ) -> list[str]:
        if route.item_usage != "pickup" or not route.referenced_items:
            return []
        return resolve_pickup_in_combat(
            character, game_state, route.referenced_items
        )

    @staticmethod
    def _execute_combat_action(
        route: ActionRouteResult,
        character: Character,
        game_state: GameState,
        *,
        user_input: str = "",
    ) -> list[str]:
        action = route.combat_action
        if action == "end_turn":
            return end_player_turn(character, game_state)

        handlers = {
            "move": lambda: [
                player_move(
                    character,
                    game_state,
                    route.move_target,
                    route.move_meters,
                    toward=route.move_toward,
                )
            ],
            "dash": lambda: [resolve_dash(character, game_state)],
            "attack": lambda: (
                GameOrchestrator._execute_pre_pickup(route, character, game_state)
                + GameOrchestrator._execute_pre_move(route, character, game_state)
                + (
                    [player_attack(character, game_state, route.attack_target, route=route)]
                    if route.attack_target
                    else []
                )
            ),
            "defend": lambda: [resolve_defend(character, game_state)],
            "flee": lambda: [resolve_flee(character, game_state)],
            "use_item": lambda: resolve_use_item_in_combat(
                character,
                game_state,
                route.referenced_items,
                cost=route.action_cost
                if route.action_cost in ("main", "bonus", "free")
                else "bonus",
                attack_target=route.attack_target,
            ),
            "interact": lambda: [
                resolve_interact(
                    character,
                    game_state,
                    route.ability,
                    route.dc,
                    proficiency_bonus=route.proficiency_bonus,
                    skill_bonus=skill_bonus_for_route(character, route),
                )
            ],
            "talk": lambda: [
                resolve_talk(
                    character,
                    game_state,
                    route.attack_target,
                    route.dc,
                    proficiency_bonus=route.proficiency_bonus,
                    skill_bonus=skill_bonus_for_route(character, route),
                    action_cost=route.action_cost
                    if route.action_cost in ("main", "bonus")
                    else "main",
                    action_intent=user_input,
                )
            ],
            "grapple": lambda: [
                resolve_grapple(character, game_state, route.attack_target, route.dc)
            ],
            "shove": lambda: [
                resolve_shove(character, game_state, route.attack_target, route.dc)
            ],
            "help": lambda: [
                resolve_help(character, game_state, route.attack_target)
            ],
            "search": lambda: [resolve_search_in_combat(character, game_state, route.dc)],
        }
        handler = handlers.get(action)
        return handler() if handler else []

    @staticmethod
    def _should_advance_combat_after_action(
        route: ActionRouteResult,
        game_state: GameState,
    ) -> bool:
        if not game_state.is_in_combat():
            return False
        combat = game_state.combat
        if not combat or not combat.is_player_turn():
            return False
        if route.combat_action == "end_turn":
            return False
        if route.ends_turn:
            return True
        return not combat.has_main_action() and not combat.has_bonus_action()

    @staticmethod
    def _execute_pre_roll(
        route: ActionRouteResult,
        character: Character,
        game_state: GameState,
        *,
        user_input: str = "",
    ) -> tuple[list[str], bool | None]:
        events: list[str] = []
        if route.roll_type == "ability_check":
            from game.check_reroll import record_ability_check
            from game.combat_modifiers import player_check_bonus

            combat = game_state.combat if game_state.is_in_combat() else None
            situational = player_check_bonus(combat, route.ability)
            hp_before = character.hp
            result = ability_check(
                character,
                route.ability,
                route.dc,
                proficiency_bonus=route.proficiency_bonus,
                skill_bonus=skill_bonus_for_route(character, route),
                situational_bonus=situational,
            )
            events.append(format_check_for_kp(result, character))
            record_ability_check(
                game_state,
                character=character,
                ability=result.ability,
                dc=result.dc,
                check_total=result.check_total or result.roll.total,
                roll_total=result.roll.total,
                success=result.success,
                action_intent=user_input,
                user_input=user_input,
                proficiency_bonus=route.proficiency_bonus,
                hp_before=hp_before,
            )
            if not result.success:
                events.extend(
                    apply_check_failure_consequences(
                        route,
                        result,
                        character,
                        game_state,
                        user_input=user_input,
                    )
                )
            return events, result.success
        if route.roll_type == "dice":
            events.append(roll(route.dice_notation).describe())
            return events, None
        return events, None

    async def _refresh_scene_map_if_needed(self, ctx: TurnContext) -> None:
        from game.turn_pipeline import _should_refresh_scene_map

        if not _should_refresh_scene_map(ctx):
            return
        await self.scene_map.aupdate(
            ctx.game_state,
            ctx.scenario,
            ctx.history,
            travel_from=ctx.map_travel_from,
        )
        ctx.game_state.map_travel_from = ""

    def refresh_scene_map(
        self,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
    ) -> bool:
        """手动刷新地图（侧边栏按钮）：触发 Map Agent 拓扑整改。"""
        return self.scene_map.update(game_state, scenario, history, reconcile=True)
