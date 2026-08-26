from chain.kp_chain import KPChain
from chain.memory import ConversationWindowMemory
from chain.memory_manager import LongTermMemoryManager
from chain.suggestions import ActionSuggester
from chain.summarizer import StorySummarizer
from config.settings import get_settings
from game.models import Character, ChatMessage, GameState
from game.results import TurnResult
from game.scenario import Scenario

START_GAME_INSTRUCTION = """\
游戏刚刚开始。请根据下方【模组信息】做开场，并全程担任引导型 KP。

开场叙事必须包含（融入故事，不要列清单、不要出戏）：
1. 场景：你在哪里，环境有什么可见/可闻的细节；
2. 处境：刚发生了什么，你为什么在这里；
3. 目标：当前最重要的一件事是什么（与 initial_quests 一致）；
4. 引导：用 1–2 句自然语言提示「你可以尝试做什么方向」，例如调查、交谈、移动、检查物品——但不要替玩家做决定。

工具：开场须 update_scene；出现 NPC 时 record_npc；若有任务尚未入库则 update_quest。
篇幅 200–400 字，结尾留明确的行动入口，让玩家知道第一句话该说什么。"""


class GameOrchestrator:
    def __init__(
        self,
        kp_chain: KPChain | None = None,
        summarizer: StorySummarizer | None = None,
        suggester: ActionSuggester | None = None,
        memory_manager: LongTermMemoryManager | None = None,
    ):
        self.kp = kp_chain if kp_chain is not None else KPChain()
        self.summarizer = summarizer if summarizer is not None else StorySummarizer()
        self.suggester = suggester if suggester is not None else ActionSuggester()
        self.memory = LongTermMemoryManager(self.summarizer) if memory_manager is None else memory_manager
        settings = get_settings()
        self.window_memory = ConversationWindowMemory(window_size=settings.max_history_messages)

    def start_game(
        self,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
    ) -> TurnResult:
        scenario.apply_to_game_state(game_state)
        game_state.started = True

        return self._finalize_turn(
            self.kp.invoke(
                character=character,
                game_state=game_state,
                scenario_context=scenario.format_for_prompt(),
                world_id=scenario.world_id,
                user_input=START_GAME_INSTRUCTION,
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
    ):
        scenario.apply_to_game_state(game_state)
        game_state.started = True
        user_input = START_GAME_INSTRUCTION
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
        enriched_input = self._maybe_add_guidance_hint(user_input, game_state.turn_count)
        turn = self.kp.invoke(
            character=character,
            game_state=game_state,
            scenario_context=scenario.format_for_prompt(),
            world_id=scenario.world_id,
            user_input=enriched_input,
            history=windowed,
        )
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
        enriched_input = self._maybe_add_guidance_hint(user_input, game_state.turn_count)
        return self._stream_turn(
            character=character,
            game_state=game_state,
            scenario=scenario,
            user_input=enriched_input,
            history=windowed,
            increment_turn=True,
            full_history=history,
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
    ):
        tool_events, text_stream = self.kp.stream(
            character=character,
            game_state=game_state,
            scenario_context=scenario.format_for_prompt(),
            world_id=scenario.world_id,
            user_input=user_input,
            history=history,
        )

        def finish(response: str) -> TurnResult:
            if increment_turn:
                game_state.turn_count += 1
                self.memory.process_after_turn(game_state, full_history or history)
            turn = TurnResult(response=response.strip(), tool_events=tool_events)
            return self._finalize_turn(
                turn, character, game_state, scenario, full_history or history
            )

        return tool_events, text_stream, finish

    def _finalize_turn(
        self,
        turn: TurnResult,
        character: Character,
        game_state: GameState,
        scenario: Scenario,
        history: list[ChatMessage],
    ) -> TurnResult:
        settings = get_settings()
        if settings.enable_action_suggestions and turn.response:
            turn.action_suggestions = self.suggester.suggest(
                game_state.current_scene,
                turn.response,
                turn_count=game_state.turn_count,
            )
        return turn

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
