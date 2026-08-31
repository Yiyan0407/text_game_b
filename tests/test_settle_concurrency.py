import asyncio
from unittest.mock import AsyncMock, MagicMock

from chain.async_utils import run_async
from game.game_config import default_game_config
from game.models import Character, GameState
from game.results import ActionRouteResult, InventoryPatch, SkillPatch, StatePatch
from game.scenario import Scenario
from game.settlement_plan import SettlementPlan
from game.turn_context import TurnContext
from game.turn_pipeline import TurnPipeline


def _noop_mechanics(*_args, **_kwargs):
    return []


def _empty_delivered(*_args, **_kwargs):
    return frozenset()


def _build_pipeline(**agent_overrides) -> TurnPipeline:
    agent_names = ("inventory_sync", "skill_sync", "time_sync", "world_sync")
    agents = {name: MagicMock() for name in agent_names}
    agents.update(agent_overrides)
    for name, agent in agents.items():
        if name not in agent_overrides:
            agent.apropose = AsyncMock(return_value=StatePatch())

    settlement_router = MagicMock()
    settlement_router.aplan = AsyncMock(
        return_value=SettlementPlan(
            inventory_sync=True,
            skill_sync=True,
            time_sync=True,
            world_sync=True,
            reason="test",
        )
    )

    return TurnPipeline(
        router=MagicMock(),
        settlement_router=settlement_router,
        inventory_sync=agents["inventory_sync"],
        skill_sync=agents["skill_sync"],
        time_sync=agents["time_sync"],
        world_sync=agents["world_sync"],
        stat_forge=MagicMock(),
        kp=MagicMock(),
        memory=MagicMock(),
        suggester=MagicMock(),
        window_memory=MagicMock(),
        resolve_mechanics=_noop_mechanics,
        delivered_item_names=_empty_delivered,
    )


def test_settle_after_kp_applies_patches_in_fixed_order():
    inventory = MagicMock()
    skill = MagicMock()
    apply_order: list[str] = []

    async def inventory_apropose(*_args, **_kwargs):
        apply_order.append("inventory_propose")
        return StatePatch(
            inventory=[
                InventoryPatch(
                    action="add",
                    item="测试物品",
                    description="测试用",
                )
            ]
        )

    async def skill_apropose(*_args, **_kwargs):
        apply_order.append("skill_propose")
        return StatePatch(
            skills=[SkillPatch(action="add", skill="测试技能", description="测试用")]
        )

    inventory.apropose = inventory_apropose
    skill.apropose = skill_apropose

    pipeline = _build_pipeline(inventory_sync=inventory, skill_sync=skill)
    pipeline.settlement_router.aplan = AsyncMock(
        return_value=SettlementPlan(
            inventory_sync=True,
            skill_sync=True,
            time_sync=False,
            world_sync=False,
            reason="test",
        )
    )
    character = Character(name="测试")
    game_state = GameState()
    scenario = Scenario(id="t", title="T", world_id="modern", opening_prompt="x")
    ctx = TurnContext(
        user_input="调查",
        character=character,
        game_state=game_state,
        scenario=scenario,
        history=[],
        route=ActionRouteResult(approved=True),
        kp_response="你找到了线索。",
        game_config=default_game_config(),
    )

    run_async(pipeline.settle_after_kp(ctx))

    assert "inventory_propose" in apply_order
    assert "skill_propose" in apply_order
    assert any("测试物品" in display for display in character.inventory_displays())
    assert "测试技能" in character.skill_names()


def test_settle_after_kp_proposes_sync_agents_concurrently():
    trace: list[str] = []

    def make_agent(name: str, delay: float = 0.05):
        agent = MagicMock()

        async def apropose(*_args, **_kwargs):
            trace.append(f"{name}_start")
            await asyncio.sleep(delay)
            trace.append(f"{name}_end")
            return StatePatch()

        agent.apropose = apropose
        return agent

    inventory = make_agent("inventory")
    skill = make_agent("skill")
    time_agent = make_agent("time")
    world = make_agent("world")

    pipeline = _build_pipeline(
        inventory_sync=inventory,
        skill_sync=skill,
        time_sync=time_agent,
        world_sync=world,
    )
    character = Character(name="测试")
    game_state = GameState()
    scenario = Scenario(id="t", title="T", world_id="modern", opening_prompt="x")
    ctx = TurnContext(
        user_input="四处看看",
        character=character,
        game_state=game_state,
        scenario=scenario,
        history=[],
        route=ActionRouteResult(approved=True),
        kp_response="你环顾四周。",
        game_config=default_game_config(),
    )

    async def run_settle():
        await pipeline.settle_after_kp(ctx)

    run_async(run_settle())

    starts = [i for i, item in enumerate(trace) if item.endswith("_start")]
    first_end = next(i for i, item in enumerate(trace) if item.endswith("_end"))
    assert len(starts) == 4
    assert all(start_idx < first_end for start_idx in starts)
