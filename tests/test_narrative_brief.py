from game.game_config import GameConfig
from game.models import GameState, ScenarioProgress
from game.narrative_brief import build_narrative_brief_static
from game.results import ActionRouteResult
from game.scenario import Scenario, ScenarioNode


def _sample_scenario() -> Scenario:
    return Scenario(
        id="test",
        title="测试",
        key_nodes=[
            ScenarioNode(
                id="node-1",
                title="开场节点",
                beats=["易玖下达任务"],
            ),
        ],
    )


def test_narrative_brief_script_guided_includes_progress():
    config = GameConfig(kp_guidance="script_guided")
    text = build_narrative_brief_static(
        "观察四周",
        ActionRouteResult(approved=True),
        [],
        game_config=config,
        scenario=_sample_scenario(),
        progress=ScenarioProgress(),
        turn_count=2,
    )
    assert "【剧本进度】" in text
    assert "易玖下达任务" in text
    assert "超出待完成 beats" in text


def test_narrative_brief_freeform_skips_progress_after_opening():
    config = GameConfig(kp_guidance="freeform")
    text = build_narrative_brief_static(
        "继续前进",
        ActionRouteResult(approved=True),
        [],
        game_config=config,
        scenario=_sample_scenario(),
        progress=ScenarioProgress(),
        turn_count=5,
    )
    assert "【剧本进度】" not in text
    assert "勿擅自推进未提及的后续情节" in text


def test_narrative_brief_balanced_allows_light_nudge():
    config = GameConfig(kp_guidance="balanced")
    text = build_narrative_brief_static(
        "搜索房间",
        ActionRouteResult(approved=True),
        [],
        game_config=config,
        scenario=_sample_scenario(),
        progress=ScenarioProgress(),
        turn_count=4,
    )
    assert "【剧本进度】" in text
    assert "环境细节呼应【剧本进度】" in text
