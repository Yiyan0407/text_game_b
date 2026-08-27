from chain.action_router import ActionRouter
from chain.opening_integrator import OpeningIntegrator
from chain.kp_chain import KPChain
from chain.memory import ConversationWindowMemory
from chain.memory_manager import LongTermMemoryManager
from chain.suggestions import ActionSuggester
from chain.summarizer import StorySummarizer
from config.settings import get_settings
from game.combat import (
    advance_after_player_action,
    end_player_turn,
    maybe_end_combat,
    player_attack,
    resolve_defend,
    resolve_flee,
    resolve_grapple,
    resolve_help,
    resolve_interact,
    resolve_search_in_combat,
    resolve_shove,
    resolve_talk,
    resolve_until_player_turn,
    resolve_use_item_in_combat,
    start_combat,
)
from game.dice import roll
from game.models import Character, ChatMessage, GameState
from game.results import ActionRouteResult, TurnResult
from game.rules import ability_check, format_check_for_kp
from game.scenario import Scenario

START_GAME_INSTRUCTION = """\
游戏刚刚开始。请根据下方【模组信息】做开场，并全程担任引导型 KP。

开场叙事必须包含（融入故事，不要列清单、不要出戏）：
1. 场景：你在哪里，环境有什么可见/可闻的细节；
2. 处境：刚发生了什么，你为什么在这里；
3. 目标：当前最重要的一件事是什么（与 initial_quests 一致）；
4. 引导：用 1–2 句自然语言提示「你可以尝试做什么方向」，例如调查、交谈、移动、检查物品——但不要替玩家做决定。

工具：开场须 update_scene；出现 NPC 时 record_npc；若有任务尚未入库则 update_quest。
篇幅 200–400 字，结尾留明确的行动入口，让玩家知道第一句话该说什么。

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
) -> str:
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
    ):
        self.kp = kp_chain if kp_chain is not None else KPChain()
        self.summarizer = summarizer if summarizer is not None else StorySummarizer()
        self.suggester = suggester if suggester is not None else ActionSuggester()
        self.memory = LongTermMemoryManager(self.summarizer) if memory_manager is None else memory_manager
        self.router = action_router if action_router is not None else ActionRouter()
        self.opening_integrator = (
            opening_integrator if opening_integrator is not None else OpeningIntegrator()
        )
        settings = get_settings()
        self.window_memory = ConversationWindowMemory(window_size=settings.max_history_messages)

    def start_game(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        *,
        career_context: str = "",
    ) -> TurnResult:
        scenario.apply_to_game_state(game_state)
        game_state.started = True

        return self._finalize_turn(
            self.kp.invoke(
                character=character,
                game_state=game_state,
                scenario_context=scenario.format_for_prompt(),
                world_id=scenario.world_id,
                user_input=_build_start_instruction(
                    character, scenario, career_context, self.opening_integrator
                ),
                history=[],
            ),
            character=character,
            game_state=game_state,
            scenario=scenario,
            history=[],
        )

    def start_game_stream(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        *,
        career_context: str = "",
    ):
        scenario.apply_to_game_state(game_state)
        game_state.started = True
        user_input = _build_start_instruction(
            character, scenario, career_context, self.opening_integrator
        )
        return self._stream_turn(
            character=character,
            game_state=game_state,
            scenario=scenario,
            user_input=user_input,
            history=[],
            increment_turn=False,
        )

    def player_turn(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        user_input: str,
        history: list[ChatMessage],
    ) -> TurnResult:
        windowed = self.window_memory.get_history(history)
        kp_input, pre_tool_events, route = self._prepare_player_input(
            user_input, character, game_state, scenario, history, windowed
        )
        if not route.approved:
            return TurnResult(
                response="",
                rejected=True,
                rejection_reason=route.rejection_reason,
            )

        skip_combat_tools = game_state.is_in_combat()
        turn = self.kp.invoke(
            character=character,
            game_state=game_state,
            scenario_context=scenario.format_for_prompt(),
            world_id=scenario.world_id,
            user_input=kp_input,
            history=windowed,
            skip_roll_tools=True,
            skip_combat_tools=skip_combat_tools,
        )
        turn.tool_events = pre_tool_events + turn.tool_events
        game_state.turn_count += 1
        self.memory.process_after_turn(game_state, history)
        return self._finalize_turn(turn, character, game_state, scenario, history)

    def player_turn_stream(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        user_input: str,
        history: list[ChatMessage],
    ):
        windowed = self.window_memory.get_history(history)
        kp_input, pre_tool_events, route = self._prepare_player_input(
            user_input, character, game_state, scenario, history, windowed
        )
        if not route.approved:
            rejected_turn = TurnResult(
                response="",
                rejected=True,
                rejection_reason=route.rejection_reason,
            )

            def finish_rejected(_response: str) -> TurnResult:
                return rejected_turn

            return rejected_turn, pre_tool_events, iter([]), finish_rejected

        skip_combat_tools = game_state.is_in_combat()
        return None, *self._stream_turn(
            character=character,
            game_state=game_state,
            scenario=scenario,
            user_input=kp_input,
            history=windowed,
            increment_turn=True,
            full_history=history,
            pre_tool_events=pre_tool_events,
            skip_roll_tools=True,
            skip_combat_tools=skip_combat_tools,
        )

    def _stream_turn(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        user_input: str,
        history: list[ChatMessage],
        increment_turn: bool,
        full_history: list[ChatMessage] | None = None,
        pre_tool_events: list[str] | None = None,
        skip_roll_tools: bool = False,
        skip_combat_tools: bool = False,
    ):
        tool_events = list(pre_tool_events or [])
        kp_tool_events, text_stream = self.kp.stream(
            character=character,
            game_state=game_state,
            scenario_context=scenario.format_for_prompt(),
            world_id=scenario.world_id,
            user_input=user_input,
            history=history,
            skip_roll_tools=skip_roll_tools,
            skip_combat_tools=skip_combat_tools,
        )

        def finish(response: str) -> TurnResult:
            if increment_turn:
                game_state.turn_count += 1
                self.memory.process_after_turn(game_state, full_history or history)
            turn = TurnResult(
                response=response.strip(),
                tool_events=tool_events + kp_tool_events,
            )
            return self._finalize_turn(
                turn, character, game_state, scenario, full_history or history
            )

        return tool_events, text_stream, finish

    def _prepare_player_input(
        self,
        user_input: str,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
        windowed: list[ChatMessage],
    ) -> tuple[str, list[str], ActionRouteResult]:
        enriched_input = self._maybe_add_guidance_hint(user_input, game_state.turn_count)
        route = self.router.evaluate(
            enriched_input, character, game_state, scenario, windowed or history
        )
        if not route.approved:
            return enriched_input, [], route

        pre_tool_events: list[str] = []

        if route.trigger_combat:
            try:
                pre_tool_events.append(
                    start_combat(character, game_state, route.enemies_spec)
                )
            except ValueError as exc:
                return enriched_input, [], ActionRouteResult(
                    approved=False,
                    rejection_reason=str(exc),
                )
            pre_tool_events.extend(resolve_until_player_turn(character, game_state))

        if game_state.is_in_combat() and route.combat_action != "none":
            combat = game_state.combat
            if combat and combat.is_player_turn():
                pre_tool_events.extend(
                    self._execute_combat_action(route, character, game_state)
                )
                if self._should_advance_combat_after_action(route, game_state):
                    pre_tool_events.extend(
                        advance_after_player_action(character, game_state)
                    )
        elif not game_state.is_in_combat() and route.needs_roll:
            pre_tool_events.append(self._execute_pre_roll(route, character))

        end_msg, _defeated = maybe_end_combat(game_state, character)
        if end_msg:
            pre_tool_events.append(end_msg)

        kp_input = self._build_kp_input(
            enriched_input, route, pre_tool_events, game_state
        )
        return kp_input, pre_tool_events, route

    @staticmethod
    def _execute_combat_action(
        route: ActionRouteResult,
        character: Character,
        game_state: GameState,
    ) -> list[str]:
        action = route.combat_action
        if action == "end_turn":
            return end_player_turn(character, game_state)

        handlers = {
            "attack": lambda: (
                [player_attack(character, game_state, route.attack_target)]
                if route.attack_target
                else []
            ),
            "defend": lambda: [resolve_defend(character, game_state)],
            "flee": lambda: [resolve_flee(character, game_state)],
            "use_item": lambda: [
                resolve_use_item_in_combat(
                    character,
                    game_state,
                    cost=route.action_cost if route.action_cost != "free" else "bonus",
                )
            ],
            "interact": lambda: [
                resolve_interact(character, game_state, route.ability, route.dc)
            ],
            "talk": lambda: [
                resolve_talk(character, game_state, route.attack_target, route.dc)
            ],
            "grapple": lambda: [
                resolve_grapple(character, game_state, route.attack_target)
            ],
            "shove": lambda: [
                resolve_shove(character, game_state, route.attack_target)
            ],
            "help": lambda: [
                resolve_help(character, game_state, route.attack_target)
            ],
            "search": lambda: [resolve_search_in_combat(character, game_state)],
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
    def _execute_pre_roll(route: ActionRouteResult, character: Character) -> str:
        if route.roll_type == "ability_check":
            result = ability_check(character, route.ability, route.dc)
            return format_check_for_kp(result, character)
        if route.roll_type == "dice":
            return roll(route.dice_notation).describe()
        return ""

    @staticmethod
    def _build_kp_input(
        user_input: str,
        route: ActionRouteResult,
        mechanical_events: list[str],
        game_state: GameState | None = None,
    ) -> str:
        in_combat = route.mode == "combat" or route.trigger_combat
        tag = "[行动裁定 — 战斗]" if in_combat else "[行动裁定 — 探索]"
        lines = [
            tag,
            f"行动意图：{route.action_intent}",
            f"叙事边界：{route.scope_stop}",
            "合理性：已通过路由检验。",
        ]
        if route.must_not_narrate:
            lines.append("本轮禁止叙事：")
            for item in route.must_not_narrate:
                lines.append(f"- {item}")
        lines.append(
            "粒度要求：只写上述行动意图的一步；到达叙事边界后立即停笔，"
            "不要链式推进到后续场景/NPC/任务。"
        )
        if in_combat and game_state and game_state.combat and game_state.combat.is_player_turn():
            lines.append(f"回合资源：{game_state.combat.format_action_economy()}")
            if game_state.combat.has_main_action() or game_state.combat.has_bonus_action():
                lines.append(
                    "玩家仍可继续本回合行动；勿提前描写回合结束，除非资源已尽或玩家结束回合。"
                )
        if mechanical_events:
            lines.append("机械结算结果：")
            for event in mechanical_events:
                lines.append(f"- {event}")
        if in_combat:
            lines.append(
                "请根据上述机械结果叙事；禁止调用 ability_check/roll_dice/"
                "start_combat/player_attack。"
            )
        elif mechanical_events:
            lines.append("请根据预掷骰结果叙事；勿再次调用 ability_check/roll_dice。")
        else:
            lines.append("该行动无需掷骰；直接叙事即可。")
        lines.append(
            "仍需按需调用 update_inventory/update_scene/update_skills 等 tools。"
        )
        lines.append("")
        lines.append(user_input)
        return "\n".join(lines)

    def _finalize_turn(
        self,
        turn: TurnResult,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
    ) -> TurnResult:
        settings = get_settings()
        if settings.enable_action_suggestions and turn.response and not turn.rejected:
            combat = game_state.combat
            turn.action_suggestions = self.suggester.suggest(
                game_state.current_scene,
                turn.response,
                turn_count=game_state.turn_count,
                in_combat=game_state.is_in_combat(),
                enemy_names=combat.living_enemy_names() if combat else [],
            )
            if not turn.action_suggestions and game_state.turn_count == 0:
                turn.action_suggestions = self._default_opening_suggestions(
                    scenario, game_state
                )
        return turn

    @staticmethod
    def _default_opening_suggestions(
        scenario: Scenario,
        game_state: GameState,
    ) -> list[str]:
        scene = game_state.current_scene or scenario.opening_scene_name or "当前场景"
        if game_state.active_quests:
            quest = game_state.active_quests[0].title
            return [
                f"观察{scene}周围",
                f"着手：{quest}",
                "和在场的人交谈",
            ]
        return [
            f"观察{scene}周围",
            "检查随身物品",
            "和在场的人交谈",
        ]

    @staticmethod
    def _maybe_add_guidance_hint(user_input: str, turn_count: int) -> str:
        text = user_input.strip()
        if not text:
            return user_input
        confused_markers = ("怎么办", "接下来", "不知道", "该怎么", "做什么", "help", "?")
        needs_guidance = (
            turn_count <= 3
            or len(text) <= 4
            or any(marker in text.lower() for marker in confused_markers)
        )
        if not needs_guidance:
            return user_input
        return (
            f"{user_input}\n\n"
            "[KP 引导：玩家可能需要方向。请用叙事方式给出 2–3 个具体可尝试的行动方向，"
            "可让 NPC/环境主动接话，不要出戏，不要列编号选项。]"
        )
