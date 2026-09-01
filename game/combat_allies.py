"""友方战斗单位：自动攻击敌人。"""

from __future__ import annotations

from game.ally_persistence import (
    apply_record_to_ally,
    init_npc_combat_record,
    is_ally_dead_in_world,
)
from game.combat_grid import move_away_m, move_toward_m
from game.combat_range import (
    MELEE_REACH_M,
    apply_ranged_melee_fallback,
    enemy_approach_meters,
    enemy_attack_range_status,
    enemy_retreat_meters,
)
from game.combat_targets import effective_unit_distance
from game.dice import roll, roll_damage
from game.effect_resolver import apply_damage_to_enemy
from game.enemy_defaults import apply_world_defaults
from game.models import CombatAlly, CombatEnemy, CombatState, GameState
from game.results import AllyDefPatch, EnemyDefPatch


def allies_from_route_defs(
    ally_defs: list,
    *,
    game_state: GameState | None = None,
    world_id: str = "",
) -> tuple[list[CombatAlly], list[str]]:
    """返回 (参战友方, 被跳过的已阵亡友方名)。"""
    allies: list[CombatAlly] = []
    skipped_dead: list[str] = []
    for item in ally_defs:
        if isinstance(item, AllyDefPatch):
            patch = item
        elif isinstance(item, EnemyDefPatch):
            patch = AllyDefPatch.model_validate(item.model_dump())
        elif isinstance(item, dict):
            patch = AllyDefPatch.model_validate(item)
        else:
            continue
        name = patch.name.strip()
        if not name or patch.hp <= 0:
            continue
        if is_ally_dead_in_world(game_state, name):
            skipped_dead.append(name)
            continue
        ally = patch.to_combat_ally()
        apply_world_defaults(ally, world_id)
        npc = game_state.find_npc(name) if game_state else None
        if npc and npc.combat and not npc.combat.dead:
            apply_record_to_ally(ally, npc.combat)
        elif game_state is not None:
            init_npc_combat_record(game_state, ally)
        allies.append(ally)
    return allies, skipped_dead


def _pick_ally_target(combat: CombatState, ally: CombatAlly) -> CombatEnemy | None:
    living = combat.fighting_enemies()
    if not living:
        return None
    return min(
        living,
        key=lambda enemy: effective_unit_distance(combat, ally.name, enemy.name),
    )


def ally_attack_enemy(
    ally: CombatAlly,
    enemy: CombatEnemy,
    combat: CombatState,
) -> str:
    dist = effective_unit_distance(combat, ally.name, enemy.name)
    in_range, range_penalty, range_note = enemy_attack_range_status(dist, ally)
    damage_override: str | None = None
    attack_style = ""
    if not in_range and "距离过近" in range_note:
        from game.combat_range import enemy_attack_profile, enemy_weapon_range_m

        profile, applied = apply_ranged_melee_fallback(
            dist,
            enemy_attack_profile(ally),
            range_m=enemy_weapon_range_m(ally),
        )
        if applied:
            in_range = True
            range_penalty = 0
            range_note = profile.label.split("（", 1)[-1].rstrip("）")
            damage_override = profile.damage_notation
            attack_style = profile.label

    range_suffix = ""
    if dist > MELEE_REACH_M or range_penalty or range_note:
        range_suffix = f"，{dist}m"
        if range_note:
            range_suffix += f" · {range_note}"

    if not in_range:
        return f"【友方】{ally.name} 够不着 {enemy.name}（{range_note or '超出射程'}，当前 {dist}m）。"

    mod = ally.attack_bonus - range_penalty
    attack_roll = roll(f"1d20{mod:+d}")
    hit = attack_roll.total >= enemy.ac
    if not hit:
        return (
            f"【友方】{ally.name} 攻击 {enemy.name}{range_suffix}："
            f"1d20[{attack_roll.rolls[0]}]{mod:+d}={attack_roll.total} vs AC {enemy.ac} → 未命中"
        )

    notation = damage_override or ally.effective_attack_damage()
    style = f"（{attack_style}）" if attack_style else ""
    damage_roll = roll_damage(notation)
    raw = damage_roll.total
    result = apply_damage_to_enemy(enemy, raw)
    detail = (
        f"【友方】{ally.name} 攻击 {enemy.name}{style}{range_suffix}："
        f"1d20[{attack_roll.rolls[0]}]{mod:+d}={attack_roll.total} vs AC {enemy.ac} → 命中！"
        f" 伤害 {damage_roll.describe()}。"
    )
    if enemy.hp <= 0:
        detail += f" {enemy.name} 被击倒！"
    else:
        detail += f" {enemy.name} 剩余 HP {enemy.hp}/{enemy.max_hp}"
        if result.fully_blocked and enemy.sp_max > 0:
            detail += f"（SP {enemy.sp}/{enemy.sp_max}）"
    return detail


def _ally_reposition(combat: CombatState, ally: CombatAlly, enemy: CombatEnemy) -> str | None:
    ally_pos = combat.get_position(ally.name)
    enemy_pos = combat.get_position(enemy.name)
    if ally_pos is None or enemy_pos is None:
        return None

    dist = effective_unit_distance(combat, ally.name, enemy.name)
    retreat = enemy_retreat_meters(ally, dist)
    if retreat > 0:
        new_pos = move_away_m(ally_pos, enemy_pos, retreat)
        combat.set_position(ally.name, new_pos)
        new_dist = effective_unit_distance(combat, ally.name, enemy.name)
        return f"【友方】{ally.name} 后撤 {retreat}m（距 {enemy.name} {new_dist}m）。"
    move = enemy_approach_meters(ally, dist)
    if move <= 0:
        return None
    new_pos = move_toward_m(ally_pos, enemy_pos, move)
    combat.set_position(ally.name, new_pos)
    new_dist = effective_unit_distance(combat, ally.name, enemy.name)
    return f"【友方】{ally.name} 靠近 {enemy.name} {move}m（距离 {new_dist}m）。"


def resolve_ally_turn(
    combat: CombatState,
    game_state: GameState,
) -> str | None:
    actor = combat.current_actor()
    ally = combat.get_ally(actor)
    if not ally or ally.hp <= 0:
        return f"【友方】{actor} 已倒下，跳过回合。"
    if not ally.can_act():
        return f"【友方】{ally.name} 已失能，跳过回合。"

    target = _pick_ally_target(combat, ally)
    if target is None:
        return f"【友方】{ally.name}：无存活敌人。"

    reposition = _ally_reposition(combat, ally, target)
    dist = effective_unit_distance(combat, ally.name, target.name)
    in_range, _, _ = enemy_attack_range_status(dist, ally)
    if in_range:
        attack = ally_attack_enemy(ally, target, combat)
        if reposition:
            return f"{reposition} {attack}"
        return attack

    if reposition:
        dist = effective_unit_distance(combat, ally.name, target.name)
        in_range, _, range_note = enemy_attack_range_status(dist, ally)
        if in_range:
            return f"{reposition} {ally_attack_enemy(ally, target, combat)}"
        return f"{reposition} 【友方】{ally.name} 仍够不着 {target.name}（{range_note}，{dist}m）。"

    _, _, range_note = enemy_attack_range_status(dist, ally)
    return f"【友方】{ally.name} 够不着 {target.name}（{range_note or '超出射程'}，{dist}m）。"


def resolve_non_player_turn(
    combat: CombatState,
    character,
    game_state: GameState,
) -> str | None:
    actor = combat.current_actor()
    if actor == "player":
        return None
    if combat.get_ally(actor):
        return resolve_ally_turn(combat, game_state)
    from game.combat import _resolve_enemy_turn

    return _resolve_enemy_turn(combat, character, game_state)
