import streamlit as st

from game.models import Character, ChatMessage, GameState
from game.results import TurnResult
from game.profile import sync_card_from_adventure
from game.save import SaveGame, SaveManager, get_action_suggestions
from game.scenario import Scenario


class SaveReloadResult:
    __slots__ = ("success", "new_messages", "turn_count", "already_latest", "error")

    def __init__(
        self,
        *,
        success: bool,
        new_messages: int = 0,
        turn_count: int = 0,
        already_latest: bool = False,
        error: str = "",
    ) -> None:
        self.success = success
        self.new_messages = new_messages
        self.turn_count = turn_count
        self.already_latest = already_latest
        self.error = error


def apply_save_to_session(save_game: SaveGame, scenario: Scenario) -> None:
    if save_game.world_id:
        scenario = scenario.model_copy(update={"world_id": save_game.world_id})
    st.session_state.character = save_game.character
    st.session_state.game_state = save_game.game_state
    st.session_state.scenario = scenario
    st.session_state.messages = save_game.messages
    st.session_state.current_save_id = save_game.save_id
    st.session_state.current_character_id = save_game.character_id or None
    st.session_state.action_suggestions = get_action_suggestions(save_game)
    st.session_state.game_started = True


def reload_current_save_from_disk() -> SaveReloadResult:
    save_id = st.session_state.get("current_save_id")
    if not save_id:
        return SaveReloadResult(success=False, error="当前没有关联存档。")

    save_manager: SaveManager | None = st.session_state.get("save_manager")
    if save_manager is None:
        return SaveReloadResult(success=False, error="存档管理器未初始化。")

    old_messages = len(st.session_state.get("messages", []))
    old_turn = getattr(st.session_state.get("game_state"), "turn_count", 0)

    try:
        save_game = save_manager.load(save_id)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        return SaveReloadResult(success=False, error=f"存档读取失败：{exc}")

    from game.scenario_loader import ScenarioNotFoundError, load_scenario

    try:
        scenario = load_scenario(save_game.scenario_id)
    except ScenarioNotFoundError:
        return SaveReloadResult(
            success=False,
            error=f"存档关联的模组「{save_game.scenario_id}」不存在。",
        )

    apply_save_to_session(save_game, scenario)
    new_messages = len(st.session_state.messages)
    turn_count = save_game.game_state.turn_count
    return SaveReloadResult(
        success=True,
        new_messages=max(0, new_messages - old_messages),
        turn_count=turn_count,
        already_latest=new_messages == old_messages and turn_count == old_turn,
    )


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
