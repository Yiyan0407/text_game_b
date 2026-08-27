from collections.abc import Iterator
from unittest.mock import MagicMock, patch

from chain.kp_chain import KPChain
from game.models import Character, GameState


def test_stream_yields_narrative_after_tool_phase():
    character = Character(name="测试")
    game_state = GameState()
    kp = KPChain()

    chunk1 = MagicMock()
    chunk1.content = "你"
    chunk2 = MagicMock()
    chunk2.content = "好"

    with patch.object(kp, "_run_tool_phase", return_value=([], [])):
        with patch.object(kp, "llm", MagicMock()) as mock_llm:
            mock_llm.stream.return_value = iter([chunk1, chunk2])
            tool_events, stream = kp.stream(
                character, game_state, "ctx", "modern", "行动", []
            )
            parts = list(stream)

    assert tool_events == []
    assert parts == ["你", "好"]
    mock_llm.stream.assert_called_once()
