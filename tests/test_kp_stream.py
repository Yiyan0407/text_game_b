from unittest.mock import MagicMock, patch

from chain.kp_chain import KPChain
from game.models import Character, GameState


def test_narrate_stream_yields_narrative_chunks():
    character = Character(name="测试")
    game_state = GameState()
    kp = KPChain()

    chunk1 = MagicMock()
    chunk1.content = "你"
    chunk2 = MagicMock()
    chunk2.content = "好"

    with patch.object(kp, "llm", MagicMock()) as mock_llm:
        mock_llm.stream.return_value = iter([chunk1, chunk2])
        stream = kp.narrate_stream(
            character,
            game_state,
            "ctx",
            "modern",
            "【叙事简报】行动",
            [],
        )
        parts = list(stream)

    assert parts == ["你", "好"]
    mock_llm.stream.assert_called_once()
