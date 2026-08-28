"""冒险运行时快照，用于流式回合失败时回滚。"""

from __future__ import annotations

from game.models import Character, GameState


def snapshot_adventure(
    character: Character,
    game_state: GameState,
) -> tuple[Character, GameState]:
    return character.model_copy(deep=True), game_state.model_copy(deep=True)


def restore_adventure(
    character: Character,
    game_state: GameState,
    char_snap: Character,
    state_snap: GameState,
) -> None:
    restored_char = char_snap.model_copy(deep=True)
    restored_state = state_snap.model_copy(deep=True)
    for field in Character.model_fields:
        setattr(character, field, getattr(restored_char, field))
    for field in GameState.model_fields:
        setattr(game_state, field, getattr(restored_state, field))
