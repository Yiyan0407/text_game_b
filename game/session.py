import streamlit as st

from game.models import Character, ChatMessage, GameState
from game.results import TurnResult
from game.save import SaveGame, SaveManager
from game.scenario import Scenario


def append_turn_result(turn: TurnResult) -> None:
    for event in turn.tool_events:
        st.session_state.messages.append(
            ChatMessage(role="system", content=f"🎲 {event}")
        )
    st.session_state.messages.append(
        ChatMessage(role="assistant", content=turn.response)
    )


def persist_save() -> None:
    character: Character | None = st.session_state.get("character")
    game_state: GameState | None = st.session_state.get("game_state")
    scenario: Scenario | None = st.session_state.get("scenario")
    if not character or not game_state or not scenario:
        return

    save_manager: SaveManager = st.session_state.save_manager
    save_id = st.session_state.current_save_id
    save_game = SaveGame.create(
        scenario_id=scenario.id,
        scenario_title=scenario.title,
        character=character,
        game_state=game_state,
        messages=st.session_state.messages,
        save_id=save_id,
        action_suggestions=st.session_state.get("action_suggestions", []),
    )
    save_manager.save(save_game)
    st.session_state.current_save_id = save_game.save_id
