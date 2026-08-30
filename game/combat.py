from __future__ import annotations

import json
import re

from game.dice import roll, roll_damage
from game.effect_resolver import apply_damage_to_enemy, apply_incoming_damage
from game.combat_range import (
    DEFAULT_START_DISTANCE_M,
    MELEE_REACH_M,
    attack_range_status,
    enemy_approach_meters,
    enemy_attack_range_status,
    movement_speed_for,
)
from game.combat_targets import effective_enemy_distance
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
    distance = _extract_int(
        data.get("distance")
        or data.get("distance_m")
        or data.get("start_distance_m")
    )
    attack_bonus = _extract_int(data.get("attack_bonus"))
    attack_damage = str(data.get("attack_damage") or data.get("damage") or "").strip()
    sp = _extract_int(data.get("sp") or data.get("SP"))
    sp_max = _extract_int(data.get("sp_max") or data.get("SP_max"))
    use_dex = bool(data.get("use_dex"))
    attack_range_normal_m = _extract_int(
        data.get("attack_range_normal_m") or data.get("attack_range_m")
    )
    attack_range_max_m = _extract_int(data.get("attack_range_max_m"))
    if not name or hp is None:
        return None
    enemy = CombatEnemy(
        name=name,
        hp=hp,
        max_hp=hp,
        ac=ac or 12,
        start_distance_m=distance or 10,
    )
    if attack_bonus is not None:
        enemy.attack_bonus = attack_bonus
    if attack_damage:
        enemy.attack_damage = attack_damage
        enemy.damage_notation = attack_damage
    if sp is not None:
        enemy.sp = max(0, sp)
    if sp_max is not None:
        enemy.sp_max = max(0, sp_max)
    if use_dex:
        enemy.use_dex = True
    if attack_range_normal_m is not None:
        enemy.attack_range_normal_m = max(0, attack_range_normal_m)
    if attack_range_max_m is not None:
        enemy.attack_range_max_m = max(0, attack_range_max_m)
    return enemy


def enemies_from_route_defs(
    enemy_defs: list,
    *,
    world_id: str = "",
) -> list[CombatEnemy]:
    from game.enemy_defaults import apply_world_defaults
    from game.results import EnemyDefPatch

    enemies: list[CombatEnemy] = []
    for item in enemy_defs:
        if isinstance(item, EnemyDefPatch):
            patch = item
        elif isinstance(item, dict):
            patch = EnemyDefPatch.model_validate(item)
        else:
            continue
        if not patch.name.strip() or patch.hp <= 0:
            continue
        enemy = patch.to_combat_enemy()
        apply_world_defaults(enemy, world_id)
        enemies.append(enemy)
    return enemies


def parse_enemies(spec: str, *, world_id: str = "") -> list[CombatEnemy]:
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
        distance = numbers[2] if len(numbers) > 2 else 10
        enemies.append(
            CombatEnemy(name=name, hp=hp, max_hp=hp, ac=ac, start_distance_m=distance)
        )

    if not enemies:
        raise ValueError("至少需要一个敌人")
    if world_id:
        from game.enemy_defaults import apply_world_defaults

        enemies = [apply_world_defaults(enemy, world_id) for enemy in enemies]
    return enemies


def player_ac(
    character: Character,
    defending: bool = False,
    *,
    game_state: GameState | None = None,
) -> int:
    from game.combat_modifiers import player_ac_bonus

    ac = character.armor_class(defending=defending)
    combat = game_state.combat if game_state else None
    return ac + player_ac_bonus(combat)


def start_combat(
    character: Character,
    game_state: GameState,
    enemies_spec: str,
    *,
    enemy_defs: list | None = None,
    world_id: str = "",
) -> str:
    if enemy_defs:
        enemies = enemies_from_route_defs(enemy_defs, world_id=world_id)
    else:
        enemies = parse_enemies(enemies_spec, world_id=world_id)
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
    speed = movement_speed_for(character)
    distances = {enemy.name: enemy.start_distance_m for enemy in enemies}

    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=enemies,
        player_initiative=player_init,
        turn_order=turn_order,
        turn_index=0,
        movement_speed_m=speed,
        movement_remaining_m=speed,
        enemy_distances=distances,
    )
    dist_text = "；".join(
        f"{enemy.name} {enemy.start_distance_m}m" for enemy in enemies
    )
    order_text = " → ".join(
        character.name if n == "player" else n for n in turn_order
    )
    return (
        f"战斗开始！先攻顺序：{order_text}。"
        f"玩家先攻 {player_init}。"
        + " ".join(f"{e.name} 先攻 {e.initiative}" for e in enemies)
        + f" 起始距离：{dist_text}。"
        + f" 你的移动力 {speed}m/回合。"
    )


def enemy_attack(
    enemy: CombatEnemy,
    character: Character,
    defending: bool = False,
    *,
    game_state: GameState | None = None,
    range_penalty: int = 0,
    distance_m: int | None = None,
    range_note: str = "",
) -> str:
    from game.combat_modifiers import enemy_attack_roll_modifier

    ac = player_ac(character, defending=defending, game_state=game_state)
    roll_mod = (
        enemy.attack_bonus
        + enemy_attack_roll_modifier(game_state.combat if game_state else None)
        - range_penalty
    )
    attack = roll(f"1d20{roll_mod:+d}")
    hit = attack.total >= ac

    range_suffix = ""
    if distance_m is not None and (range_penalty or distance_m > MELEE_REACH_M):
        range_suffix = f"，{distance_m}m"
        if range_note:
            range_suffix += f" · {range_note}"

    if not hit:
        return (
            f"{enemy.name} 攻击你{range_suffix}：1d20[{attack.rolls[0]}]{roll_mod:+d}="
            f"{attack.total} vs AC {ac} → 未命中"
        )

    damage_roll = roll_damage(enemy.effective_attack_damage())
    raw_damage = damage_roll.total
    result = apply_incoming_damage(character, raw_damage)
    events = result.format_events()
    detail = (
        f"{enemy.name} 攻击你{range_suffix}：1d20[{attack.rolls[0]}]{roll_mod:+d}="
        f"{attack.total} vs AC {ac} → 命中！伤害 {damage_roll.describe()}。"
    )
    if events:
        detail += " " + " ".join(events)
    detail += f" 你的 HP {character.hp}/{character.effective_max_hp()}"
    return detail


def _enemy_approach(combat: CombatState, enemy: CombatEnemy) -> str | None:
    """敌人回合开始时尝试靠近玩家（仅当超出攻击极限射程）。"""
    dist = effective_enemy_distance(combat, enemy.name)
    move = enemy_approach_meters(enemy, dist)
    if move <= 0:
        return None
    new_dist = dist - move
    combat.set_distance_to(enemy.name, new_dist)
    return f"{enemy.name} 靠近 {move}m（距离 {new_dist}m）。"


def _resolve_enemy_turn(
    combat: CombatState,
    character: Character,
    game_state: GameState,
) -> str | None:
    actor = combat.current_actor()
    if actor == "player":
        return None
    enemy = combat.get_enemy(actor)
    if not enemy or enemy.hp <= 0:
        return f"{actor} 已倒下，跳过回合。"
    if enemy.surrendered:
        return f"{enemy.name} 已投降，跳过回合。"
    if not enemy.can_act():
        return f"{enemy.name} 已失能，跳过回合。"
    approach = _enemy_approach(combat, enemy)
    dist = effective_enemy_distance(combat, enemy.name)
    in_range, range_penalty, range_note = enemy_attack_range_status(dist, enemy)
    if not in_range:
        out_of_range = f"{enemy.name} 够不着你（{range_note}，当前 {dist}m）。"
        if approach:
            return f"{approach} {out_of_range}"
        return out_of_range
    attack = enemy_attack(
        enemy,
        character,
        defending=combat.defending,
        game_state=game_state,
        range_penalty=range_penalty,
        distance_m=dist,
        range_note=range_note if range_penalty else "",
    )
    if approach:
        return f"{approach} {attack}"
    return attack


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
        event = _resolve_enemy_turn(combat, character, game_state)
        if event:
            events.append(event)
        combat.advance_turn()
        if combat.turn_index == start_index:
            break
        if not combat.fighting_enemies():
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
        if not combat.fighting_enemies():
            break
        if character.hp <= 0:
            break
        event = _resolve_enemy_turn(combat, character, game_state)
        if event:
            events.append(event)
        combat.advance_turn()
        if combat.turn_index == start_index:
            break
    return events


def player_move(
    character: Character,
    game_state: GameState,
    target_name: str,
    meters: int,
    *,
    toward: bool = True,
) -> str:
    combat = game_state.combat
    if not combat or not combat.active:
        return "当前不在战斗中。"
    if not combat.is_player_turn():
        actor = combat.current_actor()
        label = "玩家" if actor == "player" else actor
        return f"还没轮到你，当前是 {label} 的回合。"
    if meters <= 0:
        return "请指定移动米数。"
    if not combat.has_movement():
        return "本回合移动力已用尽。"

    enemy = combat.get_enemy(target_name)
    if not enemy or enemy.hp <= 0:
        return f"找不到存活的敌人：{target_name}"

    current = effective_enemy_distance(combat, enemy.name)
    actual = combat.spend_movement(meters)
    if actual <= 0:
        return "移动力不足，无法移动。"

    if toward:
        new_dist = max(0, current - actual)
        verb = "靠近"
    else:
        new_dist = current + actual
        verb = "远离"
    combat.set_distance_to(enemy.name, new_dist)
    return (
        f"向 {enemy.name} {verb} {actual}m，当前距离 {new_dist}m。"
        f"剩余移动力 {combat.movement_remaining_m}/{combat.movement_speed_m}m。"
    )


def resolve_dash(character: Character, game_state: GameState) -> str:
    """疾跑（Dash）：消耗主要动作，本回合移动力翻倍（再获得一次基础移动力）。"""
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
    combat.movement_remaining_m += combat.movement_speed_m
    return (
        f"你疾跑！移动力 +{combat.movement_speed_m}m，"
        f"剩余 {combat.movement_remaining_m}/{combat.movement_speed_m * 2}m（含疾跑加成）。"
    )


def player_attack(
    character: Character,
    game_state: GameState,
    target_name: str,
    use_dex: bool = False,
    route: ActionRouteResult | None = None,
) -> str:
    from game.weapon_combat import (
        draw_weapon_for_attack,
        ensure_weapon_ready,
        resolve_weapon_profile,
    )

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
    ok, draw_msg = draw_weapon_for_attack(character, combat, weapon)
    if not ok:
        combat.action_used = False
        return draw_msg
    ensure_weapon_ready(character, weapon)

    distance = effective_enemy_distance(combat, enemy.name)
    in_range, range_penalty, range_note = attack_range_status(distance, weapon)
    if not in_range:
        combat.action_used = False
        return f"无法攻击 {enemy.name}：{range_note}（当前 {distance}m）。"

    attr = "dex" if weapon.use_dex or use_dex else "str"
    mod = character.modifier(attr) + weapon.attack_bonus - range_penalty
    attack_roll = roll(f"1d20{mod:+d}")
    hit = attack_roll.total >= enemy.ac

    range_suffix = f" · {range_note}" if range_penalty or distance > MELEE_REACH_M else ""
    prefix = f"{draw_msg} " if draw_msg else ""
    if not hit:
        return (
            f"{prefix}攻击 {enemy.name}（{weapon.label}，{distance}m{range_suffix}）："
            f"1d20[{attack_roll.rolls[0]}]{mod:+d}={attack_roll.total} "
            f"vs AC {enemy.ac} → 未命中"
        )

    damage_roll = roll_damage(weapon.damage_notation)
    attr_mod = character.modifier(attr) + weapon.attack_bonus - range_penalty
    raw_damage = damage_roll.total + attr_mod
    raw_damage = max(0, raw_damage)
    dmg_result = apply_damage_to_enemy(enemy, raw_damage)
    sp_note = ""
    if dmg_result.effective_sp > 0 or dmg_result.sp_before > 0:
        if dmg_result.fully_blocked:
            sp_note = f" · 敌人 SP{dmg_result.effective_sp} 完全阻挡"
        elif dmg_result.hp_loss < raw_damage:
            sp_note = (
                f" · 敌人 SP{dmg_result.effective_sp} 阻挡 "
                f"{raw_damage - dmg_result.hp_loss} 点"
            )
        if dmg_result.sp_after < dmg_result.sp_before:
            sp_note += f" · SP {dmg_result.sp_before}→{dmg_result.sp_after}"
    result = (
        f"{prefix}攻击 {enemy.name}（{weapon.label}，{distance}m{range_suffix}）：命中！"
        f"伤害 {damage_roll.describe()}{mod:+d} = {raw_damage}。"
        f"{sp_note}"
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

    if not combat.fighting_enemies():
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


def spend_free_interact_or_error(combat: CombatState) -> str | None:
    if combat.has_free_interact():
        combat.spend_free_interact()
        return None
    return "本回合免费物件互动已用尽（拾取、拔武器、快速装备等）。"


def end_player_turn(character: Character, game_state: GameState) -> list[str]:
    combat = game_state.combat
    if not combat or not combat.active or not combat.is_player_turn():
        return ["当前无法结束回合。"]
    return advance_after_player_action(character, game_state)


_DEESCALATION_TALK_MARKERS = (
    "收刀",
    "不再攻击",
    "停止攻击",
    "放下武器",
    "缴械",
    "威慑",
    "投降",
    "举起",
    "退后",
    "住手",
    "别动",
)


def _is_deescalation_intent(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    return any(marker in cleaned for marker in _DEESCALATION_TALK_MARKERS)


def resolve_combat_ability_check(
    character: Character,
    ability: str,
    dc: int,
    label: str,
    *,
    game_state: GameState | None = None,
    proficiency_bonus: bool = False,
    skill_bonus: int = 0,
) -> str:
    from game.combat_modifiers import player_check_bonus

    combat = game_state.combat if game_state else None
    situational = player_check_bonus(combat, ability)
    result = ability_check(
        character,
        ability,
        dc,
        proficiency_bonus=proficiency_bonus,
        skill_bonus=skill_bonus,
        situational_bonus=situational,
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
    ensure_ability_check_dc(route)
    if not route.needs_roll:
        return "场景互动：缺少合法 DC。"
    return resolve_combat_ability_check(
        character,
        ability,
        route.dc,
        "场景互动",
        game_state=game_state,
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
    action_cost: str = "main",
    action_intent: str = "",
) -> str:
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return "还没轮到你行动。"
    cost = action_cost if action_cost in ("main", "bonus") else "main"
    err = spend_action_or_error(combat, cost)
    if err:
        return err
    label = f"对 {target} 交涉" if target else "战斗交涉"
    from game.combat_modifiers import player_check_bonus
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
    ensure_ability_check_dc(route)
    if not route.needs_roll:
        return f"{label}：缺少合法 DC。"
    situational = player_check_bonus(combat, "cha")
    result = ability_check(
        character,
        "cha",
        route.dc,
        proficiency_bonus=proficiency_bonus,
        skill_bonus=skill_bonus,
        situational_bonus=situational,
    )
    outcome = "成功" if result.success else "失败"
    lines = [f"{label}：{format_check_for_kp(result, character)} → {outcome}"]

    deescalation = _is_deescalation_intent(action_intent)
    if result.success and deescalation and target.strip():
        enemy = combat.get_enemy(target)
        if enemy and enemy.hp > 0:
            enemy.surrendered = True
            lines.append(f"🏳️ {enemy.name} 已投降，停止交战。")

    if not combat.fighting_enemies():
        lines.append(end_combat(game_state))

    return "\n".join(lines)


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
    ensure_ability_check_dc(route)
    if not route.needs_roll:
        return f"擒抱 {enemy.name}：缺少合法 DC。"
    return resolve_combat_ability_check(
        character, "str", route.dc, f"擒抱 {enemy.name}", game_state=game_state
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
    ensure_ability_check_dc(route)
    if not route.needs_roll:
        return f"推撞 {enemy.name}：缺少合法 DC。"
    return resolve_combat_ability_check(
        character, "str", route.dc, f"推撞 {enemy.name}", game_state=game_state
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
    ensure_ability_check_dc(route)
    if not route.needs_roll:
        return "战斗中搜索观察：缺少合法 DC。"
    return resolve_combat_ability_check(
        character, "wis", route.dc, "战斗中搜索观察", game_state=game_state
    )


def resolve_pickup_in_combat(
    character: Character,
    game_state: GameState,
    items: list[str],
) -> list[str]:
    """消耗免费物件互动；物品入库在 KP 叙事后结算。"""
    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return ["还没轮到你行动。"]
    refs = [item.strip() for item in items if item and item.strip()]
    if not refs:
        return ["没有可拾取的物品。"]
    err = spend_free_interact_or_error(combat)
    if err:
        return [err]

    return [f"免费物件互动：拾取 {item}" for item in refs]


def resolve_use_item_in_combat(
    character: Character,
    game_state: GameState,
    item_refs: list[str] | None = None,
    cost: str = "bonus",
    *,
    attack_target: str = "",
) -> list[str]:
    """消耗对应动作额度；伤害/投掷类效果在 KP 前结算，装备类仍于叙事后结算。"""
    from game.combat_item_use import combat_use_item_cost, combat_use_resolves_pre_kp
    from game.combat_targets import normalize_enemy_ref
    from game.item_use import resolve_use_item

    combat = game_state.combat
    if not combat or not combat.is_player_turn():
        return ["还没轮到你行动。"]

    refs = item_refs or []
    if not refs or not str(refs[0]).strip():
        return ["未指定要使用的物品。"]
    if not character.has_inventory_item(refs[0]):
        return [f"背包中没有：{refs[0]}"]

    if cost not in ("main", "bonus", "free"):
        cost = combat_use_item_cost(
            character,
            refs[0],
            attack_target=attack_target,
        )

    if cost == "free":
        err = spend_free_interact_or_error(combat)
    else:
        err = spend_action_or_error(combat, cost)
    if err:
        return [err]

    target = character.find_inventory_item(refs[0])
    label = target.format_detail() if target else refs[0].strip()
    cost_label = {
        "free": "免费物件互动",
        "bonus": "附加动作",
        "main": "主要动作",
    }.get(cost, "动作")
    events = [f"{cost_label}：使用 {label}"]

    if combat_use_resolves_pre_kp(character, refs[0], attack_target=attack_target):
        resolved_target = (
            normalize_enemy_ref(combat, attack_target) if attack_target.strip() else ""
        )
        events.extend(
            resolve_use_item(
                character,
                refs,
                game_state=game_state,
                attack_target=resolved_target,
            )
        )

    return events
