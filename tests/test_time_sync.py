from chain.time_sync_agent import TimeSyncAgent
from game.results import StatePatch, TimePatch


def test_time_sync_parse_minimal():
    agent = TimeSyncAgent()
    patch = agent._parse_response(
        '{"time": {"advance_minutes": 2, "advance_reason": "简短交谈"}}'
    )
    assert patch.time is not None
    assert patch.time.advance_minutes == 2
    assert patch.time.advance_reason == "简短交谈"


def test_time_sync_parse_empty():
    agent = TimeSyncAgent()
    assert agent._parse_response("{}") == StatePatch()


def test_time_sync_parse_invalid():
    agent = TimeSyncAgent()
    assert agent._parse_response("bad") == StatePatch()
