from unittest.mock import AsyncMock, MagicMock

import pytest

from chain.async_utils import run_async
from chain.settlement_router import SettlementRouterAgent
from game.models import Character, GameState
from game.results import ActionRouteResult
from game.settlement_plan import SettlementRouterError, parse_settlement_plan


def test_parse_settlement_router_response():
    agent = SettlementRouterAgent()
    plan = agent._parse_response(
        '{"tasks": {"inventory_sync": true, "skill_sync": false, '
        '"time_sync": true, "world_sync": false}, "reason": "仅对话"}'
    )
    assert plan.inventory_sync is True
    assert plan.skill_sync is False
    assert plan.time_sync is True
    assert plan.world_sync is False


def test_parse_failure_raises():
    agent = SettlementRouterAgent()
    with pytest.raises(SettlementRouterError, match="JSON 解析失败"):
        agent._parse_response("not json")


def test_aplan_invokes_llm(monkeypatch):
    agent = SettlementRouterAgent()
    mock_chain = MagicMock()
    mock_response = MagicMock()
    mock_response.content = (
        '{"tasks": {"inventory_sync": false, "skill_sync": false, '
        '"time_sync": true, "world_sync": false}, "reason": "观察"}'
    )
    mock_chain.ainvoke = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(agent, "prompt", MagicMock())
    agent.prompt.__or__ = MagicMock(return_value=mock_chain)

    plan = run_async(
        agent.aplan(
            "观察四周",
            "你环顾房间。",
            Character(name="测试"),
            GameState(),
            [],
            route=ActionRouteResult(approved=True),
        )
    )
    assert plan == parse_settlement_plan(
        {
            "tasks": {
                "inventory_sync": False,
                "skill_sync": False,
                "time_sync": True,
                "world_sync": False,
            },
            "reason": "观察",
        }
    )
