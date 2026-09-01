import asyncio
from unittest.mock import AsyncMock, MagicMock

from chain.enemy_forge_agent import EnemyForgeAgent
from game.enemy_forge import (
    collect_enemy_forge_targets,
    is_valid_enemy_def,
    merge_enemy_defs,
    names_from_enemies_spec,
)
from game.models import Character, GameState, NPCRelation
from game.results import ActionRouteResult, EnemyDefPatch
from game.scenario import Scenario
from game.turn_context import TurnContext
from game.turn_pipeline import TurnPipeline


def test_names_from_enemies_spec():
    assert names_from_enemies_spec("守卫:12:12,野狗:8:10") == ["守卫", "野狗"]


def test_collect_enemy_forge_targets_skips_valid_defs():
    route = ActionRouteResult(
        trigger_combat=True,
        enemies_spec="守卫:12:12,野狗:8:10",
        enemy_defs=[
            EnemyDefPatch(name="守卫", hp=14, ac=12),
            EnemyDefPatch(name="野狗", hp=0, ac=10),
        ],
    )
    targets, kept = collect_enemy_forge_targets(route, GameState())
    assert len(kept) == 1
    assert kept[0].name == "守卫"
    assert [item.name for item in targets] == ["野狗"]


def test_collect_enemy_forge_targets_from_hostile_npcs():
    state = GameState(
        npcs=[
            NPCRelation(name="佝偻影子", attitude="hostile", notes="持弯刀"),
            NPCRelation(name="路人", attitude="neutral"),
        ]
    )
    route = ActionRouteResult(trigger_combat=True, enemies_spec="")
    targets, kept = collect_enemy_forge_targets(route, state)
    assert kept == []
    assert len(targets) == 1
    assert targets[0].name == "佝偻影子"
    assert "弯刀" in targets[0].description


def test_merge_enemy_defs_preserves_order():
    expected = ["甲", "乙", "丙"]
    merged = merge_enemy_defs(
        [EnemyDefPatch(name="乙", hp=10, ac=11)],
        [EnemyDefPatch(name="甲", hp=12, ac=12), EnemyDefPatch(name="丙", hp=8, ac=10)],
        expected_names=expected,
    )
    assert [item.name for item in merged] == expected


def test_is_valid_enemy_def():
    assert is_valid_enemy_def(EnemyDefPatch(name="x", hp=1, ac=10))
    assert not is_valid_enemy_def(EnemyDefPatch(name="", hp=1, ac=10))
    assert not is_valid_enemy_def(EnemyDefPatch(name="x", hp=0, ac=10))


def test_aensure_combat_enemy_defs_concurrent():
    agent = EnemyForgeAgent.__new__(EnemyForgeAgent)
    forged = [
        EnemyDefPatch(name="佝偻影子", hp=14, ac=12, attack_damage="1d8"),
        EnemyDefPatch(name="魁梧影子", hp=18, ac=13, attack_damage="2d6"),
        EnemyDefPatch(name="迅捷影子", hp=12, ac=11, attack_damage="1d6"),
    ]
    agent.aforge_one = AsyncMock(side_effect=forged)  # type: ignore[method-assign]

    route = ActionRouteResult(
        trigger_combat=True,
        enemies_spec="佝偻影子:12:11,魁梧影子:12:11,迅捷影子:12:11",
        enemy_defs=[],
    )
    state = GameState(
        npcs=[
            NPCRelation(name="佝偻影子", attitude="hostile"),
            NPCRelation(name="魁梧影子", attitude="hostile"),
            NPCRelation(name="迅捷影子", attitude="hostile"),
        ]
    )
    merged, events = asyncio.run(
        agent.aensure_combat_enemy_defs(
            route,
            character=Character(name="测试"),
            game_state=state,
            scenario=Scenario(id="test", title="测试", world_id="cyberpunk"),
        )
    )
    assert len(merged) == 3
    assert agent.aforge_one.await_count == 3
    assert len(events) == 3
    assert all("EnemyForge" in event for event in events)


def test_prepare_runs_enemy_forge_before_start_combat():
    enemy_forge = MagicMock()
    enemy_forge.aensure_combat_enemy_defs = AsyncMock(
        return_value=(
            [EnemyDefPatch(name="守卫", hp=12, ac=11)],
            ["EnemyForge·守卫：HP 12 AC 11 1d6"],
        )
    )
    router = MagicMock()
    router.aevaluate = AsyncMock(
        return_value=ActionRouteResult(
            approved=True,
            trigger_combat=True,
            enemies_spec="守卫:12:11",
        )
    )
    mechanics_events: list[str] = []

    def resolve_mechanics(route, *_args, **_kwargs):
        mechanics_events.append(f"defs={len(route.enemy_defs)}")
        return ["战斗开始"]

    pipeline = TurnPipeline(
        router=router,
        settlement_router=MagicMock(),
        inventory_sync=MagicMock(),
        skill_sync=MagicMock(),
        time_sync=MagicMock(),
        world_sync=MagicMock(),
        stat_forge=MagicMock(),
        enemy_forge=enemy_forge,
        kp=MagicMock(),
        memory=MagicMock(),
        suggester=MagicMock(),
        window_memory=MagicMock(),
        resolve_mechanics=resolve_mechanics,
        delivered_item_names=lambda *_args, **_kwargs: frozenset(),
    )
    ctx = TurnContext(
        user_input="开战",
        character=Character(name="测试"),
        game_state=GameState(),
        scenario=Scenario(id="test", title="测试"),
        history=[],
    )
    assert asyncio.run(pipeline.prepare(ctx)) is True
    enemy_forge.aensure_combat_enemy_defs.assert_awaited_once()
    assert ctx.mechanical_events[0].startswith("EnemyForge")
    assert mechanics_events == ["defs=1"]
    assert ctx.mechanical_events[-1] == "战斗开始"
