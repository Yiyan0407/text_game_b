"""Action Router 解析失败或 LLM 漏判时的确定性兜底路由。"""

from __future__ import annotations

import re

from game.models import ChatMessage, GameState
from game.results import ActionRouteResult, EnemyDefPatch

_COMBAT_START_MARKERS = (
    "开战",
    "开打",
    "动手",
    "迎战",
    "进入战斗",
    "开始战斗",
    "冲上去打",
    "接战",
)

_DEFEND_MARKERS = (
    "闪避",
    "躲避",
    "格挡",
    "防御",
    "招架",
    "侧身",
    "避开",
    "躲闪",
    "闪开",
)

_END_TURN_MARKERS = (
    "结束回合",
    "结束本回合",
)

_COMBAT_NARRATIVE_MARKERS = (
    "攻击",
    "挥",
    "刺",
    "矛尖",
    "冲来",
    "敌人",
    "交手",
    "影子",
    "长矛",
    "弯刀",
    "盾",
    "先动手",
    "直刺",
    "嘶吼",
    "迎战",
    "竞技场",
)

_ATTACK_MARKERS = (
    "攻击",
    "砍向",
    "砍",
    "刺杀",
    "刺向",
    "刺",
    "杀",
    "扑向",
    "扑击",
    "斩",
    "踢向",
    "开枪",
    "射击",
    "射向",
    "打向",
    "揍",
)

_ATTACK_PRONOUN_MARKERS = (
    "攻击他",
    "攻击她",
    "攻击它",
    "砍他",
    "砍她",
    "杀他",
    "杀她",
    "打他",
    "打她",
)

_ENEMY_ROLE_HINTS: tuple[tuple[str, str, str, int, int], ...] = (
    ("长矛", "长矛手", "1d8", 14, 11),
    ("弯刀", "弯刀手", "1d6", 12, 11),
    ("盾", "持盾者", "1d6", 16, 13),
)

_CHINESE_COUNT = {
    "一": 1,
    "两": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def collect_recent_narrative(history: list[ChatMessage], *, limit: int = 10) -> str:
    parts: list[str] = []
    for msg in history[-limit:]:
        if msg.role in ("assistant", "user"):
            parts.append(msg.content)
    return "\n".join(parts)


def looks_like_combat_start(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if any(marker in normalized for marker in _COMBAT_START_MARKERS):
        return True
    if "战斗" in normalized and any(
        word in normalized for word in ("开始", "进入", "开展", "准备")
    ):
        return True
    if "开战" in normalized.replace(" ", ""):
        return True
    return False


def looks_like_defend(text: str) -> bool:
    normalized = text.strip()
    return bool(normalized) and any(marker in normalized for marker in _DEFEND_MARKERS)


def looks_like_end_turn(text: str) -> bool:
    normalized = text.strip()
    return bool(normalized) and any(marker in normalized for marker in _END_TURN_MARKERS)


def narrative_implies_imminent_combat(text: str) -> bool:
    if not text.strip():
        return False
    hits = sum(1 for marker in _COMBAT_NARRATIVE_MARKERS if marker in text)
    if hits >= 2:
        return True
    return ("刺" in text or "矛" in text) and ("你" in text or "影子" in text or "敌人" in text)


def _parse_chinese_count(token: str) -> int | None:
    token = token.strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    if token in _CHINESE_COUNT:
        return _CHINESE_COUNT[token]
    if token.startswith("十") and len(token) == 2 and token[1] in _CHINESE_COUNT:
        return 10 + _CHINESE_COUNT[token[1]]
    if token.endswith("十") and len(token) == 2 and token[0] in _CHINESE_COUNT:
        return _CHINESE_COUNT[token[0]] * 10
    return None


def _extract_enemy_count(text: str) -> int | None:
    match = re.search(
        r"([0-9]+|[一二两三四五六七八九十]+)\s*(?:个|名|位)?\s*(?:影子|敌人|对手|人形|轮廓)",
        text,
    )
    if match:
        return _parse_chinese_count(match.group(1))
    match = re.search(r"三个|两名|两个|一位", text)
    if match:
        mapping = {"三个": 3, "两名": 2, "两个": 2, "一位": 1}
        return mapping.get(match.group(0))
    return None


def _extract_start_distance_m(text: str) -> int:
    step_match = re.search(r"([0-9]+|[一二两三四五六七八九十]+)\s*步", text)
    if step_match:
        steps = _parse_chinese_count(step_match.group(1))
        if steps is not None:
            return max(2, min(steps, 150))
    meter_match = re.search(r"(\d+)\s*m", text, flags=re.IGNORECASE)
    if meter_match:
        return max(2, min(int(meter_match.group(1)), 150))
    return 15


def infer_enemy_defs(text: str, *, default_distance_m: int | None = None) -> list[EnemyDefPatch]:
    distance = default_distance_m if default_distance_m is not None else _extract_start_distance_m(text)
    defs: list[EnemyDefPatch] = []
    seen: set[str] = set()
    for keyword, name, damage, hp, ac in _ENEMY_ROLE_HINTS:
        if keyword in text and name not in seen:
            seen.add(name)
            defs.append(
                EnemyDefPatch(
                    name=name,
                    hp=hp,
                    ac=ac,
                    attack_damage=damage,
                    start_distance_m=distance,
                )
            )
    if defs:
        return defs

    count = _extract_enemy_count(text) or 1
    count = max(1, min(count, 6))
    if count == 1:
        return [
            EnemyDefPatch(
                name="敌人",
                hp=12,
                ac=11,
                attack_damage="1d6",
                start_distance_m=distance,
            )
        ]
    return [
        EnemyDefPatch(
            name=f"敌人{i + 1}",
            hp=12,
            ac=11,
            attack_damage="1d6",
            start_distance_m=distance,
        )
        for i in range(count)
    ]


def build_enemies_spec(enemy_defs: list[EnemyDefPatch]) -> str:
    return ",".join(f"{item.name}:{item.hp}:{item.ac}" for item in enemy_defs)


def looks_like_attack_on_someone(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return any(marker in normalized for marker in _ATTACK_MARKERS)


def find_npc_in_text(text: str, game_state: GameState):
    from game.models import NPCRelation

    if not text.strip():
        return None
    npcs: list[NPCRelation] = list(game_state.npcs or [])
    if not npcs:
        return None
    for npc in npcs:
        name = npc.name.strip()
        if not name:
            continue
        if name in text:
            return npc
        core = re.sub(r"[（(].+[)）]", "", name).strip()
        if core and core in text:
            return npc
        if core and any(part in text for part in core.split() if len(part) >= 2):
            return npc
    return None


def resolve_attack_target_npc(
    user_input: str,
    game_state: GameState,
    *,
    history: list[ChatMessage] | None = None,
):
    text = user_input.strip()
    npc = find_npc_in_text(text, game_state)
    if npc is not None:
        return npc
    narrative = collect_recent_narrative(history or [])
    npc = find_npc_in_text(f"{narrative}\n{text}", game_state)
    if npc is not None:
        return npc
    npcs = list(game_state.npcs or [])
    if len(npcs) == 1 and any(marker in text for marker in _ATTACK_PRONOUN_MARKERS):
        return npcs[0]
    return None


def _civilian_enemy_def(name: str) -> EnemyDefPatch:
    return EnemyDefPatch(
        name=name,
        hp=8,
        ac=10,
        attack_damage="1d4",
        start_distance_m=2,
    )


def normalize_attack_on_npc(
    route: ActionRouteResult,
    user_input: str,
    game_state: GameState,
    history: list[ChatMessage] | None,
) -> None:
    """玩家明确攻击在场 NPC 时强制开战（含 friendly/neutral），不因态度驳回。"""
    if game_state.is_in_combat() or route.trigger_combat:
        return
    text = user_input.strip()
    if not looks_like_attack_on_someone(text):
        return
    npc = resolve_attack_target_npc(text, game_state, history=history)
    if npc is None:
        return
    enemy = _civilian_enemy_def(npc.name.strip())
    route.approved = True
    route.rejection_reason = ""
    route.mode = "combat"
    route.trigger_combat = True
    route.enemies_spec = build_enemies_spec([enemy])
    route.enemy_defs = [enemy]
    route.combat_action = "none"
    route.item_usage = "none"
    route.needs_roll = False
    route.roll_type = "none"


def _combat_start_route(
    user_input: str,
    history: list[ChatMessage],
    game_state: GameState,
) -> ActionRouteResult | None:
    narrative = collect_recent_narrative(history)
    context = f"{narrative}\n{user_input.strip()}"
    if not looks_like_combat_start(user_input) and not looks_like_defend(user_input):
        return None
    if not (
        looks_like_combat_start(user_input)
        or narrative_implies_imminent_combat(context)
    ):
        return None
    enemy_defs = infer_enemy_defs(context)
    if not enemy_defs:
        return None
    return ActionRouteResult(
        approved=True,
        mode="combat",
        trigger_combat=True,
        enemies_spec=build_enemies_spec(enemy_defs),
        enemy_defs=enemy_defs,
        combat_action="none",
        item_usage="none",
    )


def _in_combat_route(user_input: str, game_state: GameState) -> ActionRouteResult | None:
    combat = game_state.combat
    if not combat or not combat.active:
        return None
    if looks_like_end_turn(user_input):
        return ActionRouteResult(
            approved=True,
            mode="combat",
            combat_action="end_turn",
            action_cost="free",
            ends_turn=True,
        )
    if looks_like_defend(user_input):
        return ActionRouteResult(
            approved=True,
            mode="combat",
            combat_action="defend",
            action_cost="main",
        )
    return None


def mechanical_fallback_route(
    user_input: str,
    game_state: GameState,
    *,
    history: list[ChatMessage] | None = None,
) -> ActionRouteResult | None:
    """LLM 路由 JSON 解析失败时的兜底。"""
    history = history or []
    if game_state.is_in_combat():
        return _in_combat_route(user_input, game_state)
    return _combat_start_route(user_input, history, game_state)


def normalize_exploration_combat_start(
    route: ActionRouteResult,
    user_input: str,
    game_state: GameState,
    history: list[ChatMessage] | None,
) -> None:
    """LLM 已返回 JSON 但未识别开战时，按玩家输入与叙事补触发战斗。"""
    if game_state.is_in_combat() or route.trigger_combat:
        return
    narrative = collect_recent_narrative(history or [])
    context = f"{narrative}\n{user_input.strip()}"
    wants_start = looks_like_combat_start(user_input)
    wants_defend = looks_like_defend(user_input)
    if not wants_start and not (wants_defend and narrative_implies_imminent_combat(context)):
        return
    if not narrative_implies_imminent_combat(context) and not wants_start:
        return
    enemy_defs = infer_enemy_defs(context)
    if not enemy_defs:
        return
    route.approved = True
    route.rejection_reason = ""
    route.mode = "combat"
    route.trigger_combat = True
    route.enemies_spec = build_enemies_spec(enemy_defs)
    route.enemy_defs = enemy_defs
    route.combat_action = "none"
    route.item_usage = "none"
    route.needs_roll = False
    route.roll_type = "none"
