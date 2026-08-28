from game.models import Quest
from game.scenario import Scenario, ScenarioEnding, ScenarioNode
from game.scenario_loader import blank_scenario_template, slugify_scenario_id
from ui.scenario_editor import build_scenario_from_editor


def test_blank_scenario_template():
    scenario = blank_scenario_template("cyberpunk")
    assert scenario.world_id == "cyberpunk"
    assert scenario.id == "draft_manual"
    assert slugify_scenario_id("霓虹迷局").startswith("manual_")


def test_build_scenario_from_editor_creates_new_id():
    draft = Scenario(id="draft_manual", title="", world_id="fantasy", is_generated=True)
    created = build_scenario_from_editor(
        draft,
        title="我的冒险",
        description="简介",
        world_id="fantasy",
        world="测试世界",
        tone="轻松",
        opening_scene_id="start",
        opening_scene_name="起点",
        opening_prompt="开场",
        custom_world_overlay="",
        quest_rows=[{"id": "q1", "title": "主线", "status": "active", "description": ""}],
        node_rows=[],
        ending_rows=[],
        creating=True,
    )
    assert created.id.startswith("manual_")
    assert created.id != "draft_manual"
    assert created.title == "我的冒险"
    assert created.is_generated is True


def test_build_scenario_from_editor_updates_fields():
    scenario = Scenario(
        id="gen_test",
        title="原标题",
        description="原简介",
        world_id="fantasy",
        is_generated=True,
    )
    updated = build_scenario_from_editor(
        scenario,
        title="新标题",
        description="新简介",
        world_id="cyberpunk",
        world="霓虹城",
        tone="紧张",
        opening_scene_id="lobby",
        opening_scene_name="大厅",
        opening_prompt="从这里开始",
        custom_world_overlay="扩展设定",
        quest_rows=[
            {"id": "q1", "title": "主线", "status": "active", "description": "做某事"},
        ],
        node_rows=[{"id": "n1", "title": "节点A", "description": "说明"}],
        ending_rows=[{"id": "e1", "title": "好结局", "condition": "完成任务"}],
    )
    assert updated.title == "新标题"
    assert updated.world_id == "cyberpunk"
    assert updated.initial_quests == [
        Quest(id="q1", title="主线", status="active", description="做某事")
    ]
    assert updated.key_nodes == [
        ScenarioNode(id="n1", title="节点A", description="说明")
    ]
    assert updated.endings == [
        ScenarioEnding(id="e1", title="好结局", condition="完成任务")
    ]
    assert updated.is_generated is True
    assert updated.id == "gen_test"
