from unittest.mock import AsyncMock, MagicMock

from game.models import Character, GameState
from game.opening_brief import OpeningBrief
from game.orchestrator import GameOrchestrator
from game.results import StatePatch, TurnResult
from game.scenario import Scenario


def test_start_game_does_not_sync_starter_skills(monkeypatch):
    scenario = Scenario(
        id="missing_fishermen",
        title="雾港失踪案",
        world_id="fantasy",
        opening_prompt="调查渔民失踪。",
    )
    character = Character(name="测试", background="灰港老渔民，常年出海打鱼")
    game_state = GameState()

    class FakeIntegrator:
        def generate(self, _character, _scenario):
            return OpeningBrief()

    fake_kp = MagicMock()
    fake_kp.anarrate = AsyncMock(
        return_value=TurnResult(response="开场", tool_events=[])
    )
    fake_state = MagicMock()
    fake_state.apropose = AsyncMock(return_value=StatePatch())

    orchestrator = GameOrchestrator(
        kp_chain=fake_kp,
        opening_integrator=FakeIntegrator(),
        state_agent=fake_state,
    )

    async def _fake_finalize(turn, *args, **kwargs):
        return turn

    monkeypatch.setattr(orchestrator, "_afinalize_turn", _fake_finalize)

    orchestrator.start_game(character, game_state, scenario)

    assert character.skill_names() == []
    invoke_input = fake_kp.anarrate.call_args.kwargs["user_input"]
    assert "【背景技能已同步】" not in invoke_input
