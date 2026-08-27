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


def test_tool_phase_handles_unknown_tool_name():
    from langchain_core.messages import AIMessage

    character = Character(name="测试")
    game_state = GameState()
    kp = KPChain()

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "update_inventry",
                "args": {},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )

    with patch.object(kp, "_build_prompt_messages") as mock_build:
        mock_tool = MagicMock()
        mock_tool.name = "update_inventory"
        mock_tool.invoke.return_value = "ok"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = ai_msg
        mock_build.return_value = ([], mock_llm, {"update_inventory": mock_tool})
        tool_events, _messages = kp._run_tool_phase(
            character, game_state, "ctx", "modern", "行动", []
        )

    assert any("未知工具" in event for event in tool_events)


def test_tool_phase_warns_when_max_rounds_exhausted():
    from langchain_core.messages import AIMessage

    character = Character(name="测试")
    game_state = GameState()
    kp = KPChain()

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "update_inventory",
                "args": {"action": "add", "item": "火把"},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )

    with patch.object(kp, "_build_prompt_messages") as mock_build:
        mock_tool = MagicMock()
        mock_tool.name = "update_inventory"
        mock_tool.invoke.return_value = "ok"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = ai_msg
        mock_build.return_value = ([], mock_llm, {"update_inventory": mock_tool})
        with patch.object(KPChain, "MAX_TOOL_ROUNDS", 1):
            tool_events, _messages = kp._run_tool_phase(
                character, game_state, "ctx", "modern", "行动", []
            )

    assert any("工具调用已达上限" in event for event in tool_events)
