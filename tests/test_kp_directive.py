from unittest.mock import AsyncMock, MagicMock

from chain.agent_context import format_recent_system_events
from chain.kp_meta_agent import KpMetaAgent, KpMetaResult, _extract_patch_from_kp_meta
from game.kp_directive import is_kp_directive, is_kp_meta_response, parse_kp_directive
from game.models import Character, GameState, Quest
from game.orchestrator import GameOrchestrator
from game.results import InventoryPatch, QuestPatch, StatePatch, TimePatch
from game.state_patch import _apply_quest, sanitize_kp_meta_patch


def test_parse_kp_directive_fullwidth():
    assert parse_kp_directive("【kp】请恢复任务") == "请恢复任务"
    assert parse_kp_directive("【KP】  hello") == "hello"


def test_parse_kp_directive_halfwidth():
    assert parse_kp_directive("[kp]回退刚才的失败") == "回退刚才的失败"


def test_parse_kp_directive_empty_body():
    assert parse_kp_directive("【kp】") == ""
    assert is_kp_directive("【kp】") is True


def test_parse_kp_directive_rejects_normal_input():
    assert parse_kp_directive("观察周围") is None
    assert is_kp_directive("前往码头") is False
    assert is_kp_directive("【kp】申诉") is True


def test_extract_patch_from_kp_meta_flat_top_level():
    patch = _extract_patch_from_kp_meta(
        {
            "response": "ok",
            "quests": [
                {
                    "quest_id": "q1",
                    "title": "任务",
                    "status": "active",
                }
            ],
            "time": {"cancel_deadline_ids": ["bomb"]},
        }
    )
    assert len(patch.quests) == 1
    assert patch.quests[0].quest_id == "q1"
    assert patch.time is not None
    assert patch.time.cancel_deadline_ids == ["bomb"]


def test_sanitize_kp_meta_patch_strips_adds_and_time():
    patch = sanitize_kp_meta_patch(
        StatePatch(
            inventory=[
                InventoryPatch(action="add", item="神器"),
                InventoryPatch(action="remove", item="空瓶"),
            ],
            time=TimePatch(
                advance_minutes=60,
                deadlines=[{"label": "新炸弹", "due_in_minutes": 10}],
                cancel_deadline_ids=["old"],
            ),
        )
    )
    assert len(patch.inventory) == 1
    assert patch.inventory[0].action == "remove"
    assert patch.time is not None
    assert patch.time.advance_minutes == 0
    assert patch.time.deadlines == []
    assert patch.time.cancel_deadline_ids == ["old"]


def test_apply_quest_fills_missing_title_from_existing():
    state = GameState(
        active_quests=[Quest(id="q1", title="原任务名", status="failed")]
    )
    message = _apply_quest(
        state,
        QuestPatch(quest_id="q1", title="", status="active"),
    )
    assert message
    assert state.active_quests[0].title == "原任务名"
    assert state.active_quests[0].status == "active"


def test_kp_meta_turn_applies_patch_without_router():
    character = Character(name="测试", hp=18, max_hp=20)
    game_state = GameState(
        active_quests=[
            Quest(id="primary-destroy-virus", title="摧毁病毒源头", status="failed")
        ]
    )
    kp_meta = MagicMock(spec=KpMetaAgent)
    kp_meta.arespond = AsyncMock(
        return_value=KpMetaResult(
            response="主任务已恢复。",
            patch=StatePatch(
                quests=[
                    QuestPatch(
                        quest_id="primary-destroy-virus",
                        title="摧毁病毒源头",
                        status="active",
                    )
                ],
                time=TimePatch(cancel_deadline_ids=["log_check"]),
            ),
        )
    )
    router = MagicMock()
    router.aevaluate = AsyncMock()

    orchestrator = GameOrchestrator(kp_meta_agent=kp_meta, action_router=router)
    turn = orchestrator.player_turn(
        character,
        game_state,
        MagicMock(format_for_prompt=lambda: "", world_id="modern"),
        "【kp】刚才不应判失败，请恢复",
        [],
    )

    assert turn.rejected is False
    assert "【KP 沟通】" in turn.response
    assert game_state.active_quests[0].status == "active"
    router.aevaluate.assert_not_called()
    kp_meta.arespond.assert_awaited_once()


def test_kp_meta_empty_body_skips_router_and_llm():
    router = MagicMock()
    router.aevaluate = AsyncMock()
    kp_meta = MagicMock(spec=KpMetaAgent)
    kp_meta.arespond = AsyncMock()

    orchestrator = GameOrchestrator(kp_meta_agent=kp_meta, action_router=router)
    turn = orchestrator.player_turn(
        Character(name="测试"),
        GameState(),
        MagicMock(format_for_prompt=lambda: "", world_id="modern"),
        "【kp】",
        [],
    )

    assert "请在 【kp】 后面写上" in turn.response
    router.aevaluate.assert_not_called()
    kp_meta.arespond.assert_not_called()


def test_kp_meta_turn_cancels_deadline():
    game_state = GameState(
        deadlines=[
            {
                "id": "log_check",
                "label": "安保检查",
                "due_at_minutes": 10,
                "status": "due",
                "consequence": "暴露",
                "created_at_minutes": 0,
            }
        ]
    )
    kp_meta = MagicMock(spec=KpMetaAgent)
    kp_meta.arespond = AsyncMock(
        return_value=KpMetaResult(
            response="时限已化解。",
            patch=StatePatch(time=TimePatch(cancel_deadline_ids=["log_check"])),
        )
    )
    orchestrator = GameOrchestrator(kp_meta_agent=kp_meta)
    orchestrator.player_turn(
        Character(name="测试"),
        game_state,
        MagicMock(format_for_prompt=lambda: "", world_id="modern"),
        "【kp】这个检查已经处理好了",
        [],
    )
    assert game_state.deadlines[0].status == "cancelled"


def test_kp_meta_turn_stream_skips_action_router():
    character = Character(name="测试")
    game_state = GameState()
    kp_meta = MagicMock(spec=KpMetaAgent)
    kp_meta.arespond = AsyncMock(
        return_value=KpMetaResult(response="好的，已记录。")
    )
    router = MagicMock()
    router.aevaluate = AsyncMock()

    orchestrator = GameOrchestrator(kp_meta_agent=kp_meta, action_router=router)
    (
        rejection,
        pre_events,
        run_state,
        stream,
        item_sync,
        mem,
        finish,
        rollback,
    ) = orchestrator.player_turn_stream(
        character,
        game_state,
        MagicMock(format_for_prompt=lambda: "", world_id="modern"),
        "【kp】系统误伤了 5 点 HP",
        [],
    )

    assert rejection is None
    assert pre_events == []
    run_state()
    assert list(stream) == ["**【KP 沟通】**\n\n好的，已记录。"]
    turn = finish("")
    assert turn.response.startswith("**【KP 沟通】**")
    router.aevaluate.assert_not_called()
    assert item_sync("") == []
    assert mem() is False


def test_kp_meta_agent_parse_top_level_quests():
    result = KpMetaAgent._parse_response(
        '{"response":"已恢复","quests":[{"quest_id":"q1","title":"测试","status":"active"}]}'
    )
    assert result.patch.quests[0].quest_id == "q1"


def test_format_recent_system_events():
    from game.models import ChatMessage

    history = [
        ChatMessage(role="user", content="观察"),
        ChatMessage(role="system", content="❌ 任务失败：[q1] 测试任务"),
        ChatMessage(role="assistant", content="你环顾四周。"),
        ChatMessage(role="system", content="⏰ 时限已到：炸弹爆炸"),
    ]
    text = format_recent_system_events(history)
    assert "任务失败" in text
    assert "时限已到" in text
    assert "你环顾四周" not in text


def test_format_recent_history_excludes_system():
    from chain.agent_context import format_recent_history
    from game.models import ChatMessage

    history = [
        ChatMessage(role="system", content="❌ 任务失败"),
        ChatMessage(role="user", content="继续"),
    ]
    text = format_recent_history(history)
    assert "继续" in text
    assert "任务失败" not in text


def test_is_kp_meta_response():
    assert is_kp_meta_response("**【KP 沟通】**\n\n已恢复。")
    assert not is_kp_meta_response("你推开大门。")
