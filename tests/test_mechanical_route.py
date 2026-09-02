from chain.action_router import ActionRouter
from chain.mechanical_route import (
    infer_enemy_defs,
    mechanical_fallback_route,
    normalize_exploration_combat_start,
    normalize_attack_on_npc,
)
from game.models import Character, ChatMessage, CombatEnemy, CombatState, GameState, NPCRelation
from game.results import ActionRouteResult


def test_mechanical_fallback_combat_start_from_narrative():
    history = [
        ChatMessage(
            role="assistant",
            content=(
                "竞技场另一端，三个影子正缓缓向你走来。"
                "它们手中握着长矛、残破的盾牌、还有一柄弯刀。"
                "距离你大约三十步远。"
            ),
        ),
    ]
    route = mechanical_fallback_route("开战", GameState(), history=history)
    assert route is not None
    assert route.approved is True
    assert route.trigger_combat is True
    assert len(route.enemy_defs) == 3
    assert route.combat_action == "none"
    names = {item.name for item in route.enemy_defs}
    assert "长矛手" in names
    assert "持盾者" in names
    assert "弯刀手" in names


def test_mechanical_fallback_defend_in_combat():
    combat = CombatState(
        active=True,
        enemies=[CombatEnemy(name="长矛手", hp=10, max_hp=10, ac=11)],
        turn_order=["player"],
        turn_index=0,
        unit_positions_m={"player": (0, 0), "长矛手": (10, 0)},
    )
    state = GameState(combat=combat)
    route = mechanical_fallback_route("侧身闪避长矛", state)
    assert route is not None
    assert route.approved is True
    assert route.combat_action == "defend"


def test_normalize_exploration_combat_start_when_llm_missed():
    history = [
        ChatMessage(
            role="assistant",
            content="长矛手举起矛尖，指向你的胸口。持盾者与弯刀手也摆开架势。",
        ),
    ]
    route = ActionRouteResult(approved=True, mode="exploration")
    normalize_exploration_combat_start(
        route,
        "进入竞技场并开战",
        GameState(),
        history,
    )
    assert route.trigger_combat is True
    assert route.enemies_spec
    assert route.enemy_defs


def test_action_router_validate_accepts_mechanical_combat_start():
    history = [
        ChatMessage(
            role="assistant",
            content="三个敌人向你逼近，长矛、盾牌与弯刀在幽光下闪烁。",
        ),
    ]
    fallback = mechanical_fallback_route("开战", GameState(), history=history)
    assert fallback is not None
    normalize_exploration_combat_start(
        fallback, "开战", GameState(), history
    )
    result = ActionRouter.validate(
        fallback,
        Character(name="玩家"),
        GameState(),
        user_input="开战",
        history=history,
    )
    assert result.approved is True
    assert result.trigger_combat is True


def test_infer_enemy_defs_uses_distance_from_steps():
    defs = infer_enemy_defs("它们停在三十步外。")
    assert defs
    assert defs[0].start_distance_m == 30


def test_normalize_attack_on_friendly_npc():
    state = GameState(
        npcs=[
            NPCRelation(
                name="蜷缩的影子（少年）",
                attitude="friendly",
                notes="试图与你交流",
            )
        ]
    )
    route = ActionRouteResult(
        approved=False,
        mode="exploration",
        rejection_reason="并非敌对目标",
    )
    normalize_attack_on_npc(route, "攻击蜷缩的影子", state, history=[])
    assert route.approved is True
    assert route.trigger_combat is True
    assert "蜷缩的影子（少年）" in route.enemies_spec
    assert route.rejection_reason == ""


def test_normalize_attack_on_npc_with_pronoun_single_npc():
    history = [
        ChatMessage(
            role="assistant",
            content="蜷缩的影子（少年）关切地望着你。",
        ),
    ]
    state = GameState(
        npcs=[
            NPCRelation(name="蜷缩的影子（少年）", attitude="friendly"),
        ]
    )
    route = ActionRouteResult(approved=False, mode="exploration")
    normalize_attack_on_npc(route, "我就要攻击他", state, history=history)
    assert route.approved is True
    assert route.trigger_combat is True
