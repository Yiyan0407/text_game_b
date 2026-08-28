from __future__ import annotations

import json
import re

from game.dice import roll
from game.models import Character, CombatEnemy, CombatState, GameState
from game.rules import ability_check, format_check_for_kp

FLEE_DC = 12
_STAT_LABELS = {"HP", "AC", "hp", "ac", "生命值", "护甲"}


def _extract_int(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    cleaned = str(value).strip().strip("'\"")
    if not cleaned or cleaned.upper() in _STAT_LABELS:
        return None
    if cleaned.isdigit():
        return int(cleaned)
    match = re.search(r"\d+", cleaned)
    return int(match.group()) if match else None


def _parse_enemy_record(data: dict) -> CombatEnemy | None:
    name = str(data.get("name") or data.get("enemy") or "").strip()
    hp = _extract_int(data.get("hp") or data.get("HP") or data.get("max_hp"))
    ac = _extract_int(data.get("ac") or data.get("AC"))
    if not name or hp is None:
        return None
    return CombatEnemy(name=name, hp=hp, max_hp=hp, ac=ac or 12)


def parse_enemies(spec: str) -> list[CombatEnemy]:
    """解析敌人描述。

    支持：
    - ``名字:HP:AC``（如 ``守卫:12:12``）
    - 带标签写法（如 ``光头壮汉:HP:30:AC:12``、``光头:'HP:30:12``）
    - JSON 数组（如 ``[{"name":"光头","hp":30,"ac":12}]``）
    """
    cleaned = spec.strip()
    if not cleaned:
        raise ValueError("至少需要一个敌人")

    if cleaned.startswith("[") or cleaned.startswith("{"):
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"无效的敌人 JSON：{exc}") from exc
        records = payload if isinstance(payload, list) else [payload]
        enemies = [
            enemy
            for item in records
            if isinstance(item, dict)
            for enemy in [_parse_enemy_record(item)]
            if enemy is not None
        ]
        if enemies:
            return enemies
        raise ValueError("敌人 JSON 中缺少 name/hp 字段")

    enemies: list[CombatEnemy] = []
    for part in cleaned.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = [token.strip().strip("'\"") for token in part.split(":") if token.strip()]
        if len(tokens) < 2:
            raise ValueError(f"无效的敌人格式: {part}，请用 名字:HP:AC")

        numbers = [
            value
            for token in tokens[1:]
            if (value := _extract_int(token)) is not None
        ]
        if not numbers:
            raise ValueError(f"无效的敌人数值: {part}，请用 名字:HP:AC")

        name = tokens[0].strip().strip("'\"")
        hp = numbers[0]
        ac = numbers[1] if len(numbers) > 1 else 12
        enemies.append(CombatEnemy(name=name, hp=hp, max_hp=hp, ac=ac))

    if not enemies:
        raise ValueError("至少需要一个敌人")
    return enemies


def player_ac(character: Character, defending: bool = False) -> int:
    return character.armor_class(defending=defending)


def start_combat(
    character: Character,
    game_state: GameState,
    enemies_spec: str,
) -> str:
    enemies = parse_enemies(enemies_spec)
    dex_mod = character.modifier("dex")
    player_init = roll(f"1d20{dex_mod:+d}").total

    for enemy in enemies:
        enemy.initiative = roll("1d20").total

    order = sorted(
        [("player", player_init)] + [(e.name, e.initiative) for e in enemies],
        key=lambda x: x[1],
        reverse=True,
    )
    turn_order = [name for name, _ in order]

    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=enemies,
        player_initiative=player_init,
        turn_order=turn_order,
        turn_index=0,
    )
    order_text = " → ".join(
        character.name if n == "player" else n for n in turn_order
    )
    return (
        f"战斗开始！先攻顺序：{order_text}。"
        f"玩家先攻 {player_init}。"
        + " ".join(f"{e.name} 先攻 {e.initiative}" for e in enemies)
    )


def enemy_attack(enemy: CombatEnemy, character: Character, defending: bool = False) -> str:
    ac = player_ac(character, defending=defending)
    attack = roll(f"1d20{enemy.attack_bonus:+d}")
    hit = attack.total >= ac

    if not hit:
        return (
            f"{enemy.name} 攻击你：1d20[{attack.rolls[0]}]{enemy.attack_bonus:+d}="
            f"{attack.total} vs AC {ac} → 未命中"
        )

    damage = roll(enemy.damage_notation)
    character.hp = max(0, character.hp - damage.total)
    return (
        f"{enemy.name} 攻击你：命中！伤害 {damage.describe()}。"
        f"你的 HP {character.hp}/{character.max_hp}"
    )


def _resolve_enemy_turn(combat: CombatState, character: Character) -> str | None:
    actor = combat.current_actor()
    if actor == "player":
        return None
    enemy = combat.get_enemy(actor)
    if not enemy or enemy.hp <= 0:
        return f"{actor} 已倒下，跳过回合。"
    return enemy_attack(enemy, character, defending=combat.defending)


def resolve_until_player_turn(character: Character, game_state: GameState) -> list[str]:
    """从当前先攻位推进，直到轮到玩家或战斗结束。"""
    combat = game_state.combat
    if not combat or not combat.active:
        return []

    events: list[str] = []
    if combat.is_player_turn():
        return events

    start_index = combat.turn_index
    for _ in range(len(combat.turn_order)):
        if combat.is_player_turn():
            break
        event = _resolve_enemy_turn(combat, character)
        if event:
            events.append(event)
        combat.advance_turn()
        if combat.turn_index == start_index:
            break
        if not combat.living_enemies():
            break
        if character.hp <= 0:
            break
    return events


def advance_after_player_action(character: Character, game_state: GameState) -> list[str]:
    """玩家行动后推进先攻，结算后续敌人回合直到再次轮到玩家。"""
    combat = game_state.combat
    if not combat or not combat.active:
        return []

    events: list[str] = []
    combat.advance_turn()

    start_index = combat.turn_index
    for _ in range(len(combat.turn_order)):
        if combat.is_player_turn():
            break
        if not combat.living_enemies():
            break
        if character.hp <= 0:
            break
        event = _resolve_enemy_turn(combat, character)
        if event:
            events.append(event)
        combat.advance_turn()
        if combat.turn_index == start_index:
            break
    return events


def player_attack(
    character: Character,
    game_state: GameState,
    target_name: str,
    use_dex: bool = False,
    route: ActionRouteResult | None = None,
) -> str:
    from game.weapon_combat import ensure_weapon_ready, resolve_weapon_profile

    combat = game_state.combat
    if not combat or not combat.active:
        return "当前不在战斗中。"

    if not combat.is_player_turn():
        actor = combat.current_actor()
        label = "玩家" if actor == "player" else actor
        return f"还没轮到你，当前是 {label} 的回合。"

    err = spend_action_or_error(combat, "main")
    if err:
        return err

    enemy = combat.get_enemy(target_name)
    if not enemy or enemy.hp <= 0:
        return f"找不到存活的敌人：{target_name}"

    weapon = resolve_weapon_profile(character, route)
    ensure_weapon_ready(character, weapon)
    attr = "dex" if weapon.use_dex or use_dex else "str"
    mod = character.modifier(attr) + weapon.attack_bonus
    attack_roll = roll(f"1d20{mod:+d}")
    hit = attack_roll.total >= enemy.ac

    if not hit:
        return (
            f"攻击 {enemy.name}（{weapon.label}）：1d20[{attack_roll.rolls[0]}]{mod:+d}={attack_roll.total} "
            f"vs AC {enemy.ac} → 未命中"
        )

    damage = roll(f"{weapon.damage_notation}{mod:+d}")
    enemy.hp = max(0, enemy.hp - damage.total)
    result = (
        f"攻击 {enemy.name}（{weapon.label}）：命中！伤害 {damage.describe()}。"
        f"{enemy.name} 剩余 HP {enemy.hp}/{enemy.max_hp}"
    )
    if enemy.hp <= 0:
        result += f" {enemy.name} 被击倒！"
    return result


def resolve_defend(character: Character, game_state: GameState) -> str:
    combat = game_state.combat
    if not combat or not combat.active:
        return "当前不在战斗中。"
    if not combat.is_player_turn():
        actor = combat.current_actor()
        label = "玩家" if actor == "player" else actor
        return f"还没轮到你，当前是 {label} 的回合。"
    err = spend_action_or_error(combat, "main")
    if err:
        return err
    combat.defending = True
    return f"你进入防御姿态，AC 提升至 {player_ac(character, defending=True)}（本回合有效）。"


def resolve_flee(character: Character, game_state: GameState) -> str:
    combat = game_state.combat
    if not combat or not combat.active:
        return "当前不在战斗中。"
    if not combat.is_player_turn():
        actor = combat.current_actor()
        label = "玩家" if actor == "player" else actor
        return f"还没轮到你，当前是 {label} 的回合。"

    err = spend_action_or_error(combat, "main")
    if err:
        return err

    result = ability_check(character, "dex", FLEE_DC)
    check_text = format_check_for_kp(result, character)
    if result.success:
        end_combat(game_state)
        return f"{check_text} 你成功脱离战斗！"
    return f"{check_text} 撤退失败，仍在战斗中。"


def maybe_end_combat(game_state: GameState, character: Character) -> tuple[str | None, bool]:
    """检查是否应结束战斗。返回 (消息, 玩家是否倒地)。"""
    combat = game_state.combat
    if not combat or not combat.active:
        return None, False

    if character.hp <= 0:
        end_combat(game_state)
        return "你已倒下，战斗结束。", True

    if not combat.living_enemies():
        msg = end_combat(game_state)
        return msg, False

    return None, False


def end_combat(game_state: GameState) -> str:
    if not game_state.combat or not game_state.combat.active:
        return "当前没有进行中的战斗。"
    game_state.combat.active = False
    game_state.combat = None
    return "战斗结束。"


def spend_action_or_error(combat: CombatState, cost: str) -> str | None:
    if cost == "free":
        return None
    if cost == "main" and combat.action_used:
        return "本回合主要动作已用尽。可使用附加动作，或输入「结束回合」。"
    if cost == "bonus" and combat.bonus_action_used:
        return "本回合附加动作已用尽。"
    if not combat.spend_action(cost):
        return "动作资源不足，无法执行该行动。"
    return None


def end_player_turn(character: Character, game_state: GameState) -> list[str]:
    combat = game_state.combat
    if not combat or not combat.active or not combat.is_player_turn():
        return ["当前无法结束回合。"]
    return advance_after_player_action(character, game_state)


def resolve_combat_ability_check(
    character: Character,
    ability: str,
    dc: int,
    label: str,
    *,
    proficiency_bonus: bool = False,
    skill_bonus: int = 0,
) -> str:
    result = ability_check(
        character,
        ability,
        dc,
        proficiency_bonus=proficiency_bonus,
        skill_bonus=skill_bonus,
    )
    outcome = "成功" if result.success else "失败"
    return f"{label}：{format_check_for_kp(result, character)} → {outcome}"


def resolve_interact(
    character: Character,
    game_state: GameState,
    ability: str,
    dc: int,
    *,
    proficiency_bonus: bool = False,
    skill_bonus: int = 0,
) -> str:
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return "还没轮到你行动。"
    err = spend_action_or_error(combat, "main")
    if err:
        return err
    ability = ability if ability in ("str", "dex", "int", "wis", "cha") else "str"
    from game.difficulty import ensure_ability_check_dc
    from game.results import ActionRouteResult

    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability=ability,
        dc=dc,
        combat_action="interact",
        mode="combat",
        proficiency_bonus=proficiency_bonus,
    )
    ensure_ability_check_dc(route, user_input="场景互动")
    return resolve_combat_ability_check(
        character,
        ability,
        route.dc,
        "场景互动",
        proficiency_bonus=proficiency_bonus,
        skill_bonus=skill_bonus,
    )


def resolve_talk(
    character: Character,
    game_state: GameState,
    target: str,
    dc: int,
    *,
    proficiency_bonus: bool = False,
    skill_bonus: int = 0,
) -> str:
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return "还没轮到你行动。"
    err = spend_action_or_error(combat, "main")
    if err:
        return err
    label = f"对 {target} 交涉" if target else "战斗交涉"
    from game.difficulty import ensure_ability_check_dc
    from game.results import ActionRouteResult

    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="cha",
        dc=dc,
        combat_action="talk",
        mode="combat",
        proficiency_bonus=proficiency_bonus,
    )
    ensure_ability_check_dc(route, user_input=label)
    return resolve_combat_ability_check(
        character,
        "cha",
        route.dc,
        label,
        proficiency_bonus=proficiency_bonus,
        skill_bonus=skill_bonus,
    )


def resolve_grapple(
    character: Character,
    game_state: GameState,
    target: str,
    dc: int = 0,
) -> str:
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return "还没轮到你行动。"
    enemy = combat.get_enemy(target) if target else None
    if not enemy or enemy.hp <= 0:
        return f"找不到存活的敌人：{target}"
    err = spend_action_or_error(combat, "main")
    if err:
        return err
    from game.difficulty import ensure_ability_check_dc
    from game.results import ActionRouteResult

    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="str",
        dc=dc,
        combat_action="grapple",
        mode="combat",
    )
    ensure_ability_check_dc(route, user_input=f"擒抱 {enemy.name}")
    return resolve_combat_ability_check(
        character, "str", route.dc, f"擒抱 {enemy.name}"
    )


def resolve_shove(
    character: Character,
    game_state: GameState,
    target: str,
    dc: int = 0,
) -> str:
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return "还没轮到你行动。"
    enemy = combat.get_enemy(target) if target else None
    if not enemy or enemy.hp <= 0:
        return f"找不到存活的敌人：{target}"
    err = spend_action_or_error(combat, "main")
    if err:
        return err
    from game.difficulty import ensure_ability_check_dc
    from game.results import ActionRouteResult

    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="str",
        dc=dc,
        combat_action="shove",
        mode="combat",
    )
    ensure_ability_check_dc(route, user_input=f"推撞 {enemy.name}")
    return resolve_combat_ability_check(
        character, "str", route.dc, f"推撞 {enemy.name}"
    )


def resolve_help(character: Character, game_state: GameState, target: str) -> str:
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return "还没轮到你行动。"
    err = spend_action_or_error(combat, "main")
    if err:
        return err
    subject = target or "盟友"
    return f"你协助 {subject}，其下次攻击获得优势（由 KP 叙事体现）。"


def resolve_search_in_combat(
    character: Character,
    game_state: GameState,
    dc: int = 0,
) -> str:
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return "还没轮到你行动。"
    err = spend_action_or_error(combat, "main")
    if err:
        return err
    from game.difficulty import ensure_ability_check_dc
    from game.results import ActionRouteResult

    route = ActionRouteResult(
        approved=True,
        needs_roll=True,
        roll_type="ability_check",
        ability="wis",
        dc=dc,
        combat_action="search",
        mode="combat",
    )
    ensure_ability_check_dc(route, user_input="战斗中搜索观察")
    return resolve_combat_ability_check(
        character, "wis", route.dc, "战斗中搜索观察"
    )


def resolve_pickup_in_combat(
    character: Character,
    game_state: GameState,
    items: list[str],
) -> list[str]:
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return ["还没轮到你行动。"]
    err = spend_action_or_error(combat, "bonus")
    if err:
        return [err]

    events: list[str] = []
    for item in items:
        if character.add_inventory_item(item):
            events.append(f"获得：{item}")
    if not events:
        return ["没有可拾取的物品。"]
    return events


def resolve_use_item_in_combat(
    character: Character,
    game_state: GameState,
    item_refs: list[str] | None = None,
    cost: str = "bonus",
) -> list[str]:
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return ["还没轮到你行动。"]

    refs = item_refs or []
    if not refs or not str(refs[0]).strip():
        return ["未指定要使用的物品。"]
    if not character.has_inventory_item(refs[0]):
        return [f"背包中没有：{refs[0]}"]

    err = spend_action_or_error(combat, cost)
    if err:
        return [err]

    from game.item_use import resolve_use_item

    return resolve_use_item(character, refs)
