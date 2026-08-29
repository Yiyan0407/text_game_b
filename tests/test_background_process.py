from game.background_process import (
    format_background_processes_for_kp,
    register_background_process,
    resolve_background_processes,
)
from game.models import Character, GameState
from game.results import BackgroundProcessPatch, StatePatch, TimePatch
from game.state_patch import apply_state_patch


def test_background_process_completes_after_duration():
    state = GameState(elapsed_minutes=12)
    register_background_process(
        state,
        BackgroundProcessPatch(
            label="CyberBreacher v4.7.3 更新",
            duration_minutes=4,
            result_fact="黑客模块CyberBreacher v4.7.3更新已完成，可随时入侵门禁系统",
            blocks_actions="入侵",
        ),
    )
    assert state.background_processes[0].status == "running"

    state.elapsed_minutes = 16
    events = resolve_background_processes(state)
    assert state.background_processes[0].status == "completed"
    assert any("黑客模块CyberBreacher v4.7.3更新已完成" in fact for fact in state.memory_facts)
    assert any("后台完成" in event for event in events)


def test_format_background_process_warns_kp_when_overdue():
    state = GameState(elapsed_minutes=20)
    register_background_process(
        state,
        BackgroundProcessPatch(label="CyberBreacher v4.7.3 更新", duration_minutes=4),
    )
    state.background_processes[0].started_at_minutes = 12
    text = format_background_processes_for_kp(state)
    assert "应已完成" in text
    assert "勿写进度条" in text


def test_apply_state_patch_registers_and_completes_on_time_advance():
    character = Character(name="里昂")
    state = GameState(elapsed_minutes=12)
    patch = StatePatch(
        background_processes=[
            BackgroundProcessPatch(
                label="CyberBreacher v4.7.3 更新",
                duration_minutes=4,
                result_fact="黑客模块更新已完成",
            )
        ],
        time=TimePatch(advance_minutes=5, advance_reason="观察环境并规划"),
    )
    events = apply_state_patch(patch, character, state)
    assert any("后台启动" in event for event in events)
    assert state.background_processes[0].status == "completed"
    assert any("后台完成" in event for event in events)
    assert state.elapsed_minutes == 17


def test_register_skips_when_memory_fact_says_completed():
    state = GameState()
    state.add_memory_facts(
        ["黑客模块CyberBreacher v4.7.3更新已完成，可随时入侵门禁系统"],
        max_facts=50,
    )
    events = register_background_process(
        state,
        BackgroundProcessPatch(label="CyberBreacher v4.7.3 更新", duration_minutes=4),
    )
    assert events == []
    assert not state.background_processes
