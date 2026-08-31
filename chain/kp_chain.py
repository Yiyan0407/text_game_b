from collections.abc import AsyncIterator, Iterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from chain.llm import create_chat_llm
from game.game_config import KpGuidance
from game.models import Character, ChatMessage, GameState
from game.kp_sanitize import sanitize_kp_narrative
from game.results import TurnResult
from prompts.templates import build_narrative_prompt


class KPChain:
    def __init__(self):
        self.llm = create_chat_llm(role="kp", streaming=True)

    def narrate(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
        *,
        kp_guidance: KpGuidance = "balanced",
    ) -> TurnResult:
        messages = self._build_narrative_messages(
            character,
            game_state,
            scenario_context,
            world_id,
            user_input,
            history,
            kp_guidance=kp_guidance,
        )
        response = self.llm.invoke(messages)
        content = sanitize_kp_narrative((response.content or "").strip())
        return TurnResult(response=content, tool_events=[])

    async def anarrate(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
        *,
        kp_guidance: KpGuidance = "balanced",
    ) -> TurnResult:
        messages = self._build_narrative_messages(
            character,
            game_state,
            scenario_context,
            world_id,
            user_input,
            history,
            kp_guidance=kp_guidance,
        )
        response = await self.llm.ainvoke(messages)
        content = sanitize_kp_narrative((response.content or "").strip())
        return TurnResult(response=content, tool_events=[])

    def narrate_stream(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
        *,
        kp_guidance: KpGuidance = "balanced",
    ) -> Iterator[str]:
        messages = self._build_narrative_messages(
            character,
            game_state,
            scenario_context,
            world_id,
            user_input,
            history,
            kp_guidance=kp_guidance,
        )

        def _stream() -> Iterator[str]:
            for chunk in self.llm.stream(messages):
                if chunk.content:
                    yield chunk.content

        return _stream()

    async def anarrate_stream(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
        *,
        kp_guidance: KpGuidance = "balanced",
    ) -> AsyncIterator[str]:
        messages = self._build_narrative_messages(
            character,
            game_state,
            scenario_context,
            world_id,
            user_input,
            history,
            kp_guidance=kp_guidance,
        )
        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield chunk.content

    def _build_narrative_messages(
        self,
        character: Character,
        game_state: GameState,
        scenario_context: str,
        world_id: str,
        user_input: str,
        history: list[ChatMessage],
        *,
        kp_guidance: KpGuidance = "balanced",
    ) -> list[BaseMessage]:
        prompt = build_narrative_prompt(world_id, kp_guidance=kp_guidance)
        prompt_value = prompt.invoke(
            {
                "character_name": character.name,
                "character_background": character.background,
                "character_abilities": character.format_abilities(),
                "hp": character.hp,
                "max_hp": character.effective_max_hp(),
                "character_inventory": character.format_inventory(),
                "character_equipment": character.format_equipment(),
                "character_skills": character.format_skills(),
                "game_state_context": game_state.format_for_prompt(),
                "scenario_context": scenario_context,
                "history": self._build_messages(history),
                "input": user_input,
            }
        )
        return list(prompt_value.to_messages())

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
