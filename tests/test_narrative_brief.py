from game.game_config import GameConfig
from game.models import Character, ChatMessage, GameState, ScenarioProgress
from game.narrative_brief import (
    build_narrative_brief,
    build_narrative_brief_static,
    merge_narrative_brief_with_state,
)
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
    assert "勿擅自推进未提及的后续主线情节" in text


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


def test_merge_brief_includes_continuity_hint():
    history = [
        ChatMessage(role="user", content="查看文件"),
        ChatMessage(
            role="assistant",
            content="你打开文件。\n\n脚步声在门外停了下来。",
        ),
    ]
    text = merge_narrative_brief_with_state(
        "【叙事简报】\n【玩家输入】\n等待并查看",
        Character(name="测试"),
        GameState(),
        history=history,
    )
    assert "【叙事接续 — 禁止复述】" in text
    assert "脚步声在门外停了下来" in text


def test_merge_brief_includes_passive_skills_for_kp():
    from game.skills import Skill

    character = Character(
        name="测试",
        skills=[Skill(name="基因改造", kind="passive", description="强化体质")],
    )
    text = merge_narrative_brief_with_state(
        "【叙事简报】\n【玩家输入】\n忍痛前进",
        character,
        GameState(),
    )
    assert "【被动技能 — 常驻生效】" in text
    assert "基因改造" in text


def test_narrative_brief_combat_start_turn_constraints():
    route = ActionRouteResult(
        approved=True,
        mode="combat",
        trigger_combat=True,
        enemies_spec="蜷缩的影子（少年）:8:10",
        combat_action="none",
    )
    events = [
        "战斗开始！先攻顺序：张三 → 蜷缩的影子（少年）。",
        "轮到你行动。请在本轮发送战斗指令（移动、攻击、防御等）。",
    ]
    text = build_narrative_brief_static("攻击少年", route, events)
    assert "【开战当回合 — 叙事硬约束】" in text
    assert "禁止" in text and "击杀" in text


def test_build_narrative_brief_passes_history():
    history = [
        ChatMessage(role="assistant", content="上一轮结尾。"),
    ]
    text = build_narrative_brief(
        "继续",
        ActionRouteResult(approved=True),
        [],
        Character(name="测试"),
        GameState(),
        history=history,
    )
    assert "【叙事接续" in text
