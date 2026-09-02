from chain.action_router import ActionRouter
from game.check_consequences import _apply_failure_damage
from game.models import Character
from game.player_death import DEATH_EVENT
from game.results import ActionRouteResult


def test_character_hp_zero_is_dead():
    character = Character(name="测试", hp=0, max_hp=20)
    assert not character.is_alive()
    assert "已死亡" in character.vitals_label()


def test_failure_damage_can_kill():
    character = Character(name="测试", hp=3, max_hp=20)
    events = _apply_failure_damage(character, 8)
    assert character.hp == 0
    assert not character.is_alive()
    assert any(DEATH_EVENT in event for event in events)


def test_action_router_rejects_when_dead():
    route = ActionRouteResult(approved=True, mode="exploration")
    result = ActionRouter.validate(
        route,
        Character(name="测试", hp=0, max_hp=20),
        __import__("game.models", fromlist=["GameState"]).GameState(),
        user_input="观察周围",
    )
    assert result.approved is False
    assert "已死亡" in result.rejection_reason


def test_death_constraints_in_narrative_brief():
    from game.narrative_brief import build_narrative_brief_static

    events = ["💀 你已死亡（HP 0）。", "你已死亡，战斗结束。"]
    text = build_narrative_brief_static(
        "【自动战斗】",
        None,
        events,
        character=Character(name="测试", hp=0, max_hp=13),
    )
    assert "【死亡结局 — 叙事硬约束】" in text
    assert "禁止" in text and "重生" in text


def test_respawn_memory_filtered_when_dead():
    from game.models import GameState
    from game.results import MemoryFactPatch, StatePatch
    from game.state_patch import apply_state_patch

    character = Character(name="测试", hp=0, max_hp=13)
    state = GameState()
    patch = StatePatch(
        memory_facts=[
            MemoryFactPatch(
                text="玩家在竞技场死亡后会复活在中央，身体完全恢复。",
                topic="arena",
            )
        ]
    )
    events = apply_state_patch(patch, character, state)
    assert not any("已记录关键事实" in event for event in events)
    assert state.memory_facts == []


def test_respawn_memory_allowed_when_alive():
    from game.models import GameState
    from game.results import MemoryFactPatch, StatePatch
    from game.state_patch import apply_state_patch

    character = Character(name="测试", hp=10, max_hp=13)
    state = GameState()
    patch = StatePatch(
        memory_facts=[
            MemoryFactPatch(text="老周师傅知道密道入口。", topic="npc")
        ]
    )
    events = apply_state_patch(patch, character, state)
    assert any("已记录关键事实" in event for event in events)
