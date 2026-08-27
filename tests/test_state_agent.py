from unittest.mock import MagicMock, patch

from chain.state_agent import StateAgent
from game.models import Character, GameState
from game.results import NpcPatch, StatePatch


def test_parse_valid_json():
    agent = StateAgent()
    text = """{"npcs": [{"name": "老王", "attitude": "neutral", "notes": "店主"}]}"""
    patch = agent._parse_response(text)
    assert len(patch.npcs) == 1
    assert patch.npcs[0].name == "老王"


def test_parse_invalid_returns_empty():
    agent = StateAgent()
    patch = agent._parse_response("not json at all")
    assert patch == StatePatch()


def test_propose_calls_llm():
    agent = StateAgent()
    character = Character(name="测试")
    game_state = GameState()

    with patch.object(
        agent,
        "_parse_response",
        return_value=StatePatch(
            npcs=[NpcPatch(name="李四", attitude="unknown", notes="证人")]
        ),
    ) as mock_parse:
        with patch.object(agent.prompt, "__or__") as mock_or:
            chain = MagicMock()
            chain.invoke.return_value = MagicMock(content="{}")
            mock_or.return_value = chain
            result = agent.propose("询问李四", character, game_state, [], [])
            mock_parse.assert_called_once()
            assert result.npcs[0].name == "李四"
