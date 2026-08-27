from collections.abc import Iterator

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from chain.llm import create_chat_llm
from chain.tools import NO_TOOL_NEEDED_NAME, create_kp_tools
from game.models import Character, ChatMessage, GameState
from game.results import TurnResult
from prompts.templates import build_kp_prompt

_NARRATIVE_NUDGE = "请根据以上工具结果与玩家行动，输出本轮 KP 叙事（第二人称）。不要调用工具。"


def _merge_ai_chunks(chunks: list[AIMessageChunk]) -> AIMessage:
    if not chunks:
        return AIMessage(content="")
    merged = chunks[0]
    for chunk in chunks[1:]:
        merged = merged + chunk
    return AIMessage(
        content=merged.content,
        tool_calls=getattr(merged, "tool_calls", None) or [],
    )


def _partition_tool_calls(tool_calls: list) -> tuple[list, list]:
    state_calls = []
    no_tool_calls = []
    for tool_call in tool_calls:
        if tool_call["name"] == NO_TOOL_NEEDED_NAME:
            no_tool_calls.append(tool_call)
        else:
            state_calls.append(tool_call)
    return state_calls, no_tool_calls


class KPChain:
    MAX_TOOL_ROUNDS = 5

    def __init__(self):
        self.llm = create_chat_llm(streaming=True)

    def invoke(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
        *,
        skip_roll_tools: bool = False,
        skip_combat_tools: bool = False,
    ) -> TurnResult:
        tool_events, messages = self._run_tool_phase(
            character=character,
            game_state=game_state,
            scenario_context=scenario_context,
            world_id=world_id,
            user_input=user_input,
            history=history,
            skip_roll_tools=skip_roll_tools,
            skip_combat_tools=skip_combat_tools,
        )
        narrative_messages = list(messages)
        narrative_messages.append(HumanMessage(content=_NARRATIVE_NUDGE))
        response = self.llm.invoke(narrative_messages)
        content = (response.content or "").strip()
        return TurnResult(response=content, tool_events=tool_events)

    def stream(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
        *,
        skip_roll_tools: bool = False,
        skip_combat_tools: bool = False,
    ) -> tuple[list[str], Iterator[str]]:
        tool_events, messages = self._run_tool_phase(
            character=character,
            game_state=game_state,
            scenario_context=scenario_context,
            world_id=world_id,
            user_input=user_input,
            history=history,
            skip_roll_tools=skip_roll_tools,
            skip_combat_tools=skip_combat_tools,
        )
        narrative_messages = list(messages)
        narrative_messages.append(HumanMessage(content=_NARRATIVE_NUDGE))

        def _narrative_stream() -> Iterator[str]:
            for chunk in self.llm.stream(narrative_messages):
                if chunk.content:
                    yield chunk.content

        return tool_events, _narrative_stream()

    def run_tool_loop(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
    ) -> tuple[list[str], list[BaseMessage], AIMessage]:
        tool_events, messages = self._run_tool_phase(
            character, game_state, scenario_context, world_id, user_input, history
        )
        narrative_messages = list(messages)
        narrative_messages.append(HumanMessage(content=_NARRATIVE_NUDGE))
        final_msg = self.llm.invoke(narrative_messages)
        return tool_events, narrative_messages, final_msg

    def _run_tool_phase(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
        *,
        skip_roll_tools: bool = False,
        skip_combat_tools: bool = False,
    ) -> tuple[list[str], list[BaseMessage]]:
        messages, llm_with_tools, tool_map = self._build_prompt_messages(
            character,
            game_state,
            scenario_context,
            world_id,
            user_input,
            history,
            skip_roll_tools=skip_roll_tools,
            skip_combat_tools=skip_combat_tools,
        )
        tool_events: list[str] = []

        for _ in range(self.MAX_TOOL_ROUNDS):
            ai_msg = llm_with_tools.invoke(messages)
            if not ai_msg.tool_calls:
                messages.append(ai_msg)
                return tool_events, messages

            state_calls, no_tool_calls = _partition_tool_calls(ai_msg.tool_calls)
            messages.append(ai_msg)

            for tool_call in state_calls:
                tool_name = tool_call["name"]
                if tool_name not in tool_map:
                    result = f"未知工具：{tool_name}。请改用已注册的工具。"
                    tool_events.append(result)
                    messages.append(
                        ToolMessage(content=result, tool_call_id=tool_call["id"])
                    )
                    continue
                tool = tool_map[tool_name]
                result = tool.invoke(tool_call["args"])
                tool_events.append(str(result))
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )

            for tool_call in no_tool_calls:
                tool = tool_map[NO_TOOL_NEEDED_NAME]
                result = tool.invoke(tool_call["args"])
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )

            if no_tool_calls:
                return tool_events, messages

        warning = (
            f"工具调用已达上限（{self.MAX_TOOL_ROUNDS} 轮）。"
            "请基于当前已更新的游戏状态直接输出叙事，勿再调用工具。"
        )
        tool_events.append(warning)
        messages.append(SystemMessage(content=warning))
        return tool_events, messages

    def _build_prompt_messages(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
        *,
        skip_roll_tools: bool = False,
        skip_combat_tools: bool = False,
    ) -> tuple[list[BaseMessage], object, dict]:
        prompt = build_kp_prompt(world_id)
        tools = create_kp_tools(
            character,
            game_state,
            exclude_roll_tools=skip_roll_tools,
            exclude_combat_tools=skip_combat_tools,
        )
        llm_with_tools = self.llm.bind_tools(tools, tool_choice="required")
        tool_map = {tool.name: tool for tool in tools}

        prompt_value = prompt.invoke(
            {
                "character_name": character.name,
                "character_background": character.background,
                "character_abilities": character.format_abilities(),
                "hp": character.hp,
                "max_hp": character.max_hp,
                "character_inventory": character.format_inventory(),
                "character_skills": character.format_skills(),
                "game_state_context": game_state.format_for_prompt(),
                "scenario_context": scenario_context,
                "history": self._build_messages(history),
                "input": user_input,
            }
        )
        return list(prompt_value.to_messages()), llm_with_tools, tool_map

    @staticmethod
    def _build_messages(history: list[ChatMessage]) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        for msg in history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))
            elif msg.role == "system":
                messages.append(SystemMessage(content=msg.content))
        return messages
