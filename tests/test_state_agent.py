from unittest.mock import MagicMock, patch

from chain.world_state_agent import WorldStateAgent
from game.models import Character, GameState
from game.results import NpcPatch, StatePatch


def test_parse_valid_json():
    agent = WorldStateAgent()
    text = """{"npcs": [{"name": "老王", "attitude": "neutral", "notes": "店主"}]}"""
    patch = agent._parse_response(text)
    assert len(patch.npcs) == 1
    assert patch.npcs[0].name == "老王"


def test_parse_invalid_returns_empty():
    agent = WorldStateAgent()
    patch = agent._parse_response("not json at all")
    assert patch == StatePatch()


def test_propose_calls_llm():
    agent = WorldStateAgent()
    character = Character(name="测试")
    game_state = GameState()
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = MagicMock(content="{}")

    with patch.object(
        agent,
        "_parse_response",
        return_value=StatePatch(
            npcs=[NpcPatch(name="李四", attitude="unknown", notes="证人")]
        ),
    ) as mock_parse:
        # Python 3 对实例上的 __or__ 补丁无效，需 patch 类方法。
        with patch.object(type(agent.prompt), "__or__", return_value=mock_chain):
            result = agent.propose("询问李四", character, game_state, [], [])
            mock_parse.assert_called_once()
            mock_chain.invoke.assert_called_once()
            assert result.npcs[0].name == "李四"
