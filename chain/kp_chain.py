from collections.abc import Iterator

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from chain.llm import create_chat_llm
from chain.tools import create_kp_tools
from game.models import Character, ChatMessage, GameState
from game.results import TurnResult
from prompts.templates import build_kp_prompt


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
    ) -> TurnResult:
        tool_events, messages, final_msg, _ = self._run_tool_loop(
            character=character,
            game_state=game_state,
            scenario_context=scenario_context,
            world_id=world_id,
            user_input=user_input,
            history=history,
        )
        if final_msg.content and not final_msg.tool_calls:
            return TurnResult(response=final_msg.content.strip(), tool_events=tool_events)
        response = self.llm.invoke(messages)
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
    ) -> tuple[list[str], Iterator[str]]:
        messages, llm_with_tools, tool_map = self._build_prompt_messages(
            character, game_state, scenario_context, world_id, user_input, history
        )
        tool_events: list[str] = []

        def _narrative_stream() -> Iterator[str]:
            nonlocal messages
            for _ in range(self.MAX_TOOL_ROUNDS):
                chunks: list[AIMessageChunk] = []
                saw_tools = False
                for chunk in llm_with_tools.stream(messages):
                    chunks.append(chunk)
                    if chunk.tool_call_chunks or getattr(chunk, "tool_calls", None):
                        saw_tools = True
                    elif chunk.content and not saw_tools:
                        yield chunk.content

                ai_msg = _merge_ai_chunks(chunks)
                if not ai_msg.tool_calls:
                    return

                messages.append(ai_msg)
                for tool_call in ai_msg.tool_calls:
                    tool = tool_map[tool_call["name"]]
                    result = tool.invoke(tool_call["args"])
                    tool_events.append(str(result))
                    messages.append(
                        ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                    )

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
        tool_events, messages, final_msg, _ = self._run_tool_loop(
            character, game_state, scenario_context, world_id, user_input, history
        )
        return tool_events, messages, final_msg

    def _build_prompt_messages(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
    ) -> tuple[list[BaseMessage], object, dict]:
        prompt = build_kp_prompt(world_id)
        tools = create_kp_tools(character, game_state)
        llm_with_tools = self.llm.bind_tools(tools)
        tool_map = {tool.name: tool for tool in tools}

        prompt_value = prompt.invoke(
            {
                "character_name": character.name,
                "character_background": character.background,
                "character_abilities": character.format_abilities(),
                "hp": character.hp,
                "max_hp": character.max_hp,
                "character_inventory": character.format_inventory(),
                "game_state_context": game_state.format_for_prompt(),
                "scenario_context": scenario_context,
                "history": self._build_messages(history),
                "input": user_input,
            }
        )
        return list(prompt_value.to_messages()), llm_with_tools, tool_map

    def _run_tool_loop(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
    ) -> tuple[list[str], list[BaseMessage], AIMessage, object]:
        messages, llm_with_tools, tool_map = self._build_prompt_messages(
            character, game_state, scenario_context, world_id, user_input, history
        )
        tool_events: list[str] = []

        for _ in range(self.MAX_TOOL_ROUNDS):
            ai_msg = llm_with_tools.invoke(messages)
            if not ai_msg.tool_calls:
                return tool_events, messages, ai_msg, llm_with_tools

            messages.append(ai_msg)
            for tool_call in ai_msg.tool_calls:
                tool = tool_map[tool_call["name"]]
                result = tool.invoke(tool_call["args"])
                tool_events.append(str(result))
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )

        fallback = llm_with_tools.invoke(messages)
        return tool_events, messages, fallback, llm_with_tools

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
