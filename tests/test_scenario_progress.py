from game.game_config import GameConfig, apply_guidance_hint
from game.models import GameState, ScenarioProgress
from game.scenario import Scenario, ScenarioNode
from game.scenario_progress import (
    advance_if_node_complete,
    beat_key,
    beat_matches_corpus,
    detect_completed_beats,
    ensure_scenario_progress,
    format_progress_for_kp,
    is_node_overdue,
    node_beats,
    pending_beats,
    update_scenario_progress_after_turn,
)


def _sample_scenario() -> Scenario:
    return Scenario(
        id="test",
        title="测试模组",
        key_nodes=[
            ScenarioNode(
                id="node-arrival",
                title="降落纽约",
                description="落地后选择伪装并收到多方通讯。",
                beats=["德国特工通讯响起", "黑客串台频道出现"],
            ),
            ScenarioNode(
                id="node-lab",
                title="病毒实验室",
                description="在 B20 遇到江一燕。",
                beats=["江一燕出场"],
            ),
        ],
    )


def test_node_beats_fallback_to_description():
    node = ScenarioNode(id="n1", title="测试", description="整段描述作为 beat")
    assert node_beats(node) == ["整段描述作为 beat"]


def test_pending_beats_excludes_completed():
    scenario = _sample_scenario()
    progress = ScenarioProgress(
        completed_beat_keys=[beat_key("node-arrival", 0)],
    )
    pending = pending_beats(scenario, progress)
    assert pending == ["黑客串台频道出现"]


def test_beat_matches_corpus_by_keywords():
    assert beat_matches_corpus(
        "德国特工通讯响起",
        "加密频道里传来德语口音，一名德国特工要求你把病毒交给荒坂。",
    )


def test_detect_and_advance_node():
    scenario = _sample_scenario()
    state = GameState()
    progress = ensure_scenario_progress(state)
    events = update_scenario_progress_after_turn(
        state,
        scenario,
        kp_text="德国特工通过通讯器联系你，要求把样本交给荒坂公司。",
        state_events=["已记录 NPC：德国特工（unknown）"],
    )
    assert beat_key("node-arrival", 0) in progress.completed_beat_keys
    assert events

    update_scenario_progress_after_turn(
        state,
        scenario,
        kp_text="第二个频道接入，黑客玩家串台捣乱。",
        state_events=[],
    )
    assert progress.active_node_index == 1
    assert "node-arrival" in progress.completed_node_ids


def test_is_node_overdue_script_guided():
    progress = ScenarioProgress(
        turns_on_active_node=4,
        last_beat_completed_turn=0,
    )
    assert is_node_overdue(
        progress,
        "script_guided",
        turn_count=10,
        has_pending=True,
    )


def test_format_progress_for_kp_script_includes_pending():
    scenario = _sample_scenario()
    progress = ScenarioProgress()
    text = format_progress_for_kp(
        scenario,
        progress,
        "script_guided",
        turn_count=3,
    )
    assert "【剧本进度】" in text
    assert "德国特工通讯响起" in text
    assert "待完成要素" in text


def test_format_progress_for_kp_freeform_minimal():
    scenario = _sample_scenario()
    progress = ScenarioProgress()
    assert format_progress_for_kp(scenario, progress, "freeform", turn_count=5) == ""
    opening = format_progress_for_kp(scenario, progress, "freeform", turn_count=1)
    assert "降落纽约" in opening


def test_advance_if_node_complete():
    scenario = _sample_scenario()
    progress = ScenarioProgress(
        completed_beat_keys=[
            beat_key("node-arrival", 0),
            beat_key("node-arrival", 1),
        ],
    )
    assert advance_if_node_complete(scenario, progress) is True
    assert progress.active_node_index == 1


def test_apply_guidance_hint_script_guided_with_pending_beats():
    scenario = _sample_scenario()
    progress = ScenarioProgress()
    config = GameConfig(kp_guidance="script_guided")
    result = apply_guidance_hint(
        "检查周围",
        10,
        config,
        scenario=scenario,
        progress=progress,
    )
    assert "待完成要素" in result or "key_nodes" in result


def test_apply_guidance_hint_balanced_periodic_nudge():
    scenario = _sample_scenario()
    progress = ScenarioProgress(turns_on_active_node=8)
    config = GameConfig(kp_guidance="balanced")
    result = apply_guidance_hint(
        "沿走廊前进",
        20,
        config,
        scenario=scenario,
        progress=progress,
    )
    assert "剧本" in result
