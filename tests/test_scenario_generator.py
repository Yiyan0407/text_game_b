import pytest

from chain.scenario_generator import (
    ScenarioGenerationError,
    _extract_json,
    _normalize_scenario_data,
)
from game.scenario import Scenario
from game.scenario_loader import save_scenario, load_scenario


SAMPLE_SCENARIO_JSON = """
{
  "id": "test_gen",
  "title": "测试剧本",
  "description": "一段测试简介",
  "world_id": "cyberpunk",
  "world": "霓虹都市",
  "tone": "紧张",
  "opening_scene_id": "start",
  "opening_scene_name": "起点",
  "opening_prompt": "故事从这里开始",
  "custom_world_overlay": "企业统治一切。",
  "initial_quests": [{"id": "q1", "title": "任务", "status": "active", "description": "做某事"}],
  "key_nodes": [{"id": "n1", "title": "节点", "description": "某处"}],
  "endings": [{"id": "e1", "title": "结局", "condition": "完成"}]
}
"""


def test_extract_json_from_text():
    data = _extract_json("前缀\n" + SAMPLE_SCENARIO_JSON + "\n后缀")
    assert data["title"] == "测试剧本"


def test_extract_json_invalid():
    with pytest.raises(ScenarioGenerationError):
        _extract_json("no json here")


def test_normalize_scenario_data():
    data = _normalize_scenario_data({"title": "Hello World!"}, "modern")
    assert data["id"].startswith("gen_")
    assert data["world_id"] == "modern"


def test_save_and_load_generated(tmp_path, monkeypatch):
    import game.scenario_loader as loader

    monkeypatch.setattr(loader, "GENERATED_DIR", tmp_path)
    scenario = Scenario.model_validate(_extract_json(SAMPLE_SCENARIO_JSON))
    save_scenario(scenario, generated=True)
    loaded = load_scenario("test_gen")
    assert loaded.title == "测试剧本"
    assert loaded.is_generated is True
