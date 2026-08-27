from unittest.mock import MagicMock

from game.models import Character, GameState
from game.opening_brief import OpeningBrief
from game.orchestrator import GameOrchestrator
from game.scenario import Scenario


def test_start_game_syncs_starter_skills_from_background(monkeypatch):
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
            return OpeningBrief(starter_skills=[])

    fake_kp = MagicMock()
    fake_kp.invoke.return_value = MagicMock(
        response="开场",
        tool_events=[],
        summary_updated=False,
        rejected=False,
        rejection_reason="",
    )

    orchestrator = GameOrchestrator(
        kp_chain=fake_kp,
        opening_integrator=FakeIntegrator(),
    )
    monkeypatch.setattr(
        orchestrator,
        "_finalize_turn",
        lambda turn, **kwargs: turn,
    )

    orchestrator.start_game(character, game_state, scenario)

    assert "航海" in character.skill_names()
    invoke_input = fake_kp.invoke.call_args.kwargs["user_input"]
    assert "【背景技能已同步】" in invoke_input
