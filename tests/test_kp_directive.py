from unittest.mock import AsyncMock, MagicMock

from chain.agent_context import format_recent_system_events
from chain.kp_meta_agent import KpMetaAgent, KpMetaResult, _extract_patch_from_kp_meta
from game.kp_directive import is_kp_directive, is_kp_meta_response, parse_kp_directive
from game.models import Character, GameState, Quest
from game.orchestrator import GameOrchestrator
from game.results import EquipmentPatch, InventoryPatch, QuestPatch, StatePatch, TimePatch
from game.state_patch import _apply_quest, apply_state_patch, sanitize_kp_meta_patch


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


def test_sanitize_kp_meta_patch_keeps_inventory_and_strips_time():
    patch = sanitize_kp_meta_patch(
        StatePatch(
            inventory=[
                InventoryPatch(
                    action="add",
                    item="战斗义体·神经反应增幅模块",
                    quantity=1,
                    unit="套",
                    kind="durable",
                    description="已植入",
                ),
                InventoryPatch(action="remove", item="空瓶"),
            ],
            equipment=[
                EquipmentPatch(action="equip", item="战斗义体·神经反应增幅模块", slot="body"),
            ],
            time=TimePatch(
                advance_minutes=60,
                time_label="第1天 02:20",
                deadlines=[{"label": "新炸弹", "due_in_minutes": 10}],
                cancel_deadline_ids=["old"],
            ),
        )
    )
    assert len(patch.inventory) == 2
    assert patch.inventory[0].action == "add"
    assert len(patch.equipment) == 1
    assert patch.equipment[0].slot == "body"
    assert patch.time is not None
    assert patch.time.advance_minutes == 0
    assert patch.time.deadlines == []
    assert patch.time.time_label == "第1天 02:20"
    assert patch.time.cancel_deadline_ids == ["old"]


def test_kp_meta_sync_correction_applies_inventory_and_equipment():
    character = Character(name="里昂")
    game_state = GameState()
    patch = sanitize_kp_meta_patch(
        StatePatch(
            inventory=[
                InventoryPatch(
                    action="add",
                    item="义眼·战术扫描阵列",
                    quantity=1,
                    unit="套",
                    kind="durable",
                    description="已植入",
                ),
            ],
            equipment=[
                EquipmentPatch(action="equip", item="义眼·战术扫描阵列", slot="body"),
            ],
        )
    )
    events = apply_state_patch(patch, character, game_state, apply_time=False)
    assert character.has_inventory_item("义眼·战术扫描阵列")
    assert character.is_item_equipped("义眼·战术扫描阵列")
    assert any("装备" in event for event in events)


def test_apply_quest_requires_title():
    state = GameState(
        active_quests=[Quest(id="q1", title="原任务名", status="failed")]
    )
    message = _apply_quest(
        state,
        QuestPatch(quest_id="q1", title="", status="active"),
    )
    assert message == ""
    assert state.active_quests[0].title == "原任务名"
    assert state.active_quests[0].status == "failed"


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


def test_kp_meta_turn_runs_stat_forge_for_new_items():
    from unittest.mock import AsyncMock, MagicMock

    from chain.stat_forge_agent import StatForgeAgent
    from game.results import EquipmentPatch, InventoryPatch

    character = Character(name="里昂")
    game_state = GameState()
    kp_meta = MagicMock(spec=KpMetaAgent)
    kp_meta.arespond = AsyncMock(
        return_value=KpMetaResult(
            response="已补登记义体。",
            patch=StatePatch(
                inventory=[
                    InventoryPatch(
                        action="add",
                        item="皮下合金骨架强化",
                        quantity=1,
                        unit="套",
                        kind="durable",
                        description="已植入",
                    ),
                ],
                equipment=[
                    EquipmentPatch(
                        action="equip", item="皮下合金骨架强化", slot="body"
                    ),
                ],
            ),
        )
    )
    stat_forge = MagicMock(spec=StatForgeAgent)
    stat_forge.aforge = AsyncMock(return_value=["StatForge·皮下合金骨架强化：SP 18/18"])

    orchestrator = GameOrchestrator(kp_meta_agent=kp_meta, stat_forge_agent=stat_forge)
    turn = orchestrator.player_turn(
        character,
        game_state,
        MagicMock(format_for_prompt=lambda: "", world_id="cyberpunk"),
        "【kp】补登记义体",
        [],
    )

    assert character.is_item_equipped("皮下合金骨架强化")
    stat_forge.aforge.assert_awaited_once()
    assert any("StatForge" in event for event in turn.tool_events)


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


def test_kp_meta_turn_corrects_narrative_clock():
    game_state = GameState(story_start_absolute_minutes=8 * 60, elapsed_minutes=15)
    kp_meta = MagicMock(spec=KpMetaAgent)
    kp_meta.arespond = AsyncMock(
        return_value=KpMetaResult(
            response="已将叙事时间修正为第1天 02:20。",
            patch=StatePatch(time=TimePatch(time_label="第1天 02:20")),
        )
    )
    orchestrator = GameOrchestrator(kp_meta_agent=kp_meta)
    orchestrator.player_turn(
        Character(name="测试"),
        game_state,
        MagicMock(format_for_prompt=lambda: "", world_id="modern"),
        "【kp】叙事写凌晨2:17，系统时间却是8:15",
        [],
    )
    assert game_state.narrative_time_label == "第1天 02:20"


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
        finish,
        turn_context,
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
    assert turn_context is None
    run_state()
    assert list(stream) == ["**【KP 沟通】**\n\n好的，已记录。"]
    turn = finish("")
    assert turn.response.startswith("**【KP 沟通】**")
    router.aevaluate.assert_not_called()
    assert item_sync("") == []


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
