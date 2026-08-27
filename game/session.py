import streamlit as st

from game.models import Character, ChatMessage, GameState
from game.results import TurnResult
from game.profile import (
    CharacterCard,
    prepare_card_for_new_campaign,
    sync_card_from_adventure,
)
from game.save import SaveGame, SaveManager
from game.scenario import Scenario


def sync_character_card_to_library(*, finalize: bool = False) -> None:
    """将当前冒险进度同步到角色卡（长期角色履历）。"""
    character: Character | None = st.session_state.get("character")
    game_state: GameState | None = st.session_state.get("game_state")
    scenario: Scenario | None = st.session_state.get("scenario")
    profile_id = st.session_state.get("current_profile_id")
    card_id = st.session_state.get("current_character_id")
    if not all([character, game_state, scenario, profile_id, card_id]):
        return

    profile_manager = st.session_state.profile_manager
    try:
        card = profile_manager.load_character_card(profile_id, card_id)
    except FileNotFoundError:
        return

    sync_card_from_adventure(
        card,
        character,
        game_state,
        scenario,
        finalize=finalize,
    )
    profile_manager.save_character_card(profile_id, card)


def append_tool_events(tool_events: list[str]) -> None:
    for event in tool_events:
        text = str(event).strip()
        if not text:
            continue
        st.session_state.messages.append(
            ChatMessage(role="system", content=text)
        )


def append_turn_result(turn: TurnResult) -> None:
    append_tool_events(turn.tool_events)
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
        profile_id=st.session_state.get("current_profile_id") or "",
        character_id=st.session_state.get("current_character_id") or "",
        world_id=scenario.world_id,
    )
    save_manager.save(save_game)
    st.session_state.current_save_id = save_game.save_id
    sync_character_card_to_library()
