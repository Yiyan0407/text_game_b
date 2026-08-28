from unittest.mock import AsyncMock, MagicMock

from chain.kp_meta_agent import KpMetaAgent, KpMetaResult
from game.kp_directive import is_kp_directive, parse_kp_directive
from game.models import Character, GameState, Quest
from game.orchestrator import GameOrchestrator
from game.results import QuestPatch, StatePatch, TimePatch


def test_parse_kp_directive_fullwidth():
    assert parse_kp_directive("【kp】请恢复任务") == "请恢复任务"
    assert parse_kp_directive("【KP】  hello") == "hello"


def test_parse_kp_directive_halfwidth():
    assert parse_kp_directive("[kp]回退刚才的失败") == "回退刚才的失败"


def test_parse_kp_directive_rejects_normal_input():
    assert parse_kp_directive("观察周围") is None
    assert parse_kp_directive("【kp】") is None
    assert is_kp_directive("前往码头") is False
    assert is_kp_directive("【kp】申诉") is True


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
