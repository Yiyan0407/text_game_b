from collections.abc import Iterator
from unittest.mock import MagicMock, patch

from chain.kp_chain import KPChain
from game.models import Character, GameState


def test_stream_yields_multiple_live_chunks():
    character = Character(name="测试")
    game_state = GameState()
    kp = KPChain()

    chunk1 = MagicMock()
    chunk1.content = "你"
    chunk1.tool_calls = []
    chunk1.tool_call_chunks = []
    chunk2 = MagicMock()
    chunk2.content = "好"
    chunk2.tool_calls = []
    chunk2.tool_call_chunks = []

    final_msg = MagicMock()
    final_msg.content = "你好"
    final_msg.tool_calls = []

    with patch.object(kp, "_build_prompt_messages") as mock_build:
        mock_llm = MagicMock()
        mock_llm.stream.return_value = iter([chunk1, chunk2])
        mock_llm.invoke = MagicMock()
        mock_build.return_value = ([], mock_llm, {})

        with patch("chain.kp_chain._merge_ai_chunks", return_value=final_msg):
            tool_events, stream = kp.stream(
                character, game_state, "ctx", "modern", "行动", []
            )
            parts = list(stream)

    assert tool_events == []
    assert parts == ["你", "好"]
