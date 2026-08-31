"""主动/被动技能：行为差异与数值常驻。"""

from game.effect_resolver import (
    get_effective_sp,
    sum_passive_skill_max_hp_bonus,
)
from game.effects import EntityEffects
from game.models import Character, GameState
from game.results import ActionRouteResult, SkillPatch, StatePatch
from game.settlement_plan import SettlementPlan, ensure_skill_sync_for_acquisition
from game.skills import Skill
from game.state_patch import apply_state_patch


def _passive(name: str, **effects_kw) -> Skill:
    return Skill(
        name=name,
        description="测试被动",
        kind="passive",
        effects=EntityEffects(forged=True, **effects_kw),
    )


def test_passive_skill_max_hp_always_applies():
    character = Character(name="测试", max_hp=10, hp=10)
    character.skills.append(_passive("基因改造", max_hp_bonus=8))
    assert sum_passive_skill_max_hp_bonus(character) == 8
    assert character.effective_max_hp() == 18


def test_passive_skill_sp_always_applies():
    character = Character(name="测试", skills=[_passive("恶魔契约", sp=12, sp_max=12)])
    sp, source = get_effective_sp(character)
    assert sp == 12
    assert source == "恶魔契约"


def test_apply_passive_skill_patch():
    character = Character(name="测试")
    game_state = GameState()
    patch = StatePatch(
        skills=[
            SkillPatch(
                action="add",
                skill="神选之躯",
                description="被神明标记",
                kind="passive",
            )
        ]
    )
    events = apply_state_patch(patch, character, game_state)
    assert any("被动技能" in event for event in events)
    assert character.passive_skills()[0].name == "神选之躯"


def test_learn_route_forces_skill_sync():
    route = ActionRouteResult(approved=True, skill_usage="learn")
    plan = SettlementPlan(
        inventory_sync=True,
        skill_sync=False,
        time_sync=True,
        world_sync=True,
        reason="测试",
    )
    merged = ensure_skill_sync_for_acquisition(route, plan)
    assert merged.skill_sync is True


def test_passive_skill_not_blocked_by_unrelated_roll_failure():
    character = Character(name="测试")
    game_state = GameState()
    route = ActionRouteResult(approved=True, item_usage="use")
    patch = StatePatch(
        skills=[SkillPatch(action="add", skill="基因改造", kind="passive")]
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=["DEX 检定 1d20 = 5 vs DC 15 → 失败 ✗"],
    )
    assert not any("跳过技能添加" in event for event in events)
    assert character.passive_skills()[0].name == "基因改造"


def test_active_skill_blocked_when_learn_failed():
    character = Character(name="测试")
    game_state = GameState()
    route = ActionRouteResult(approved=True, skill_usage="learn")
    patch = StatePatch(
        skills=[SkillPatch(action="add", skill="潜行", kind="active")]
    )
    events = apply_state_patch(
        patch,
        character,
        game_state,
        route=route,
        mechanical_events=["DEX 检定 1d20 = 5 vs DC 15 → 失败 ✗"],
    )
    assert any("跳过技能添加" in event for event in events)
    assert not character.skills


def test_format_skills_groups_active_and_passive():
    character = Character(
        name="测试",
        skills=[
            Skill(name="潜行", description="隐蔽"),
            Skill(name="基因改造", kind="passive", description="强化"),
        ],
    )
    text = character.format_skills()
    assert "主动：" in text
    assert "被动：" in text
    assert "基因改造" in text
