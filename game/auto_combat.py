"""自动战斗：纯机械模拟 + 结算简报。"""

from __future__ import annotations

from dataclasses import dataclass

from game.combat import (
    advance_after_player_action,
    end_player_turn,
    maybe_end_combat,
    player_attack,
    player_move,
    resolve_until_player_turn,
)
from game.combat_range import attack_range_status, weapon_range_m
from game.combat_targets import effective_enemy_distance
from game.models import Character, CombatEnemy, CombatState, GameState
from game.results import ActionRouteResult
from game.weapon_combat import resolve_best_weapon_profile

MAX_AUTO_COMBAT_ROUNDS = 100


@dataclass
class AutoCombatResult:
    events: list[str]
    outcome: str
    rounds: int = 0


def format_auto_combat_user_input(result: AutoCombatResult) -> str:
    outcome_label = {
        "victory": "玩家获胜",
        "defeat": "玩家倒下",
        "stalemate": "战斗超时仍未结束",
        "not_in_combat": "不在战斗中",
    }.get(result.outcome, result.outcome)
    return (
        "【自动战斗】玩家委托系统代跑剩余战斗。"
        f"系统已完整模拟 {result.rounds} 个战斗轮次，结果：{outcome_label}。"
        "请根据【已发生的结果】写一段连贯的战斗描写（交锋过程→结局），"
        "不要逐条复读系统日志，但命中/伤害/倒地/受击须与机械一致。"
    )


def _nearest_living_enemy(combat: CombatState) -> CombatEnemy | None:
    living = combat.living_enemies()
    if not living:
        return None
    return min(living, key=lambda enemy: effective_enemy_distance(combat, enemy.name))


def _player_auto_step(character: Character, game_state: GameState) -> str | None:
    combat = game_state.combat
    if not combat or not combat.active or not combat.is_player_turn():
        return None

    enemy = _nearest_living_enemy(combat)
    if enemy is None:
        return None

    dist = effective_enemy_distance(combat, enemy.name)
    weapon = resolve_best_weapon_profile(character, None, distance_m=dist)
    in_range, _, _ = attack_range_status(dist, weapon)

    if not in_range and combat.has_movement():
        _, _, hard_max = weapon_range_m(weapon)
        if dist > hard_max:
            move = min(combat.movement_remaining_m, dist - hard_max)
            if move > 0:
                return player_move(
                    character,
                    game_state,
                    enemy.name,
                    move,
                    toward=True,
                )

    dist = effective_enemy_distance(combat, enemy.name)
    weapon = resolve_best_weapon_profile(character, None, distance_m=dist)
    in_range, _, _ = attack_range_status(dist, weapon)
    if in_range and combat.has_main_action():
        weapon_ref = weapon.item_name or weapon.label.split("（", 1)[0].strip()
        route = ActionRouteResult(approved=True, referenced_items=[weapon_ref])
        return player_attack(character, game_state, enemy.name, route=route)

    if combat.has_movement() and combat.movement_remaining_m > 0 and dist > 0:
        return player_move(
            character,
            game_state,
            enemy.name,
            min(combat.movement_remaining_m, dist),
            toward=True,
        )

    return None


def _summarize_outcome(
    character: Character,
    game_state: GameState,
    *,
    rounds: int,
) -> str:
    if character.hp <= 0:
        return "defeat"
    if not game_state.is_in_combat():
        return "victory"
    if rounds >= MAX_AUTO_COMBAT_ROUNDS:
        return "stalemate"
    return "stalemate"


def run_auto_combat(character: Character, game_state: GameState) -> AutoCombatResult:
    """模拟战斗至结束或达到轮次上限。仅在战斗中调用。"""
    if not game_state.is_in_combat():
        return AutoCombatResult(events=[], outcome="not_in_combat")

    events: list[str] = ["[自动战斗] 系统开始代跑战斗……"]
    rounds = 0

    while game_state.is_in_combat() and rounds < MAX_AUTO_COMBAT_ROUNDS:
        combat = game_state.combat
        if combat is None:
            break

        if not combat.is_player_turn():
            events.extend(resolve_until_player_turn(character, game_state))
            end_msg, _ = maybe_end_combat(game_state, character)
            if end_msg:
                events.append(end_msg)
            continue

        while game_state.is_in_combat() and game_state.combat.is_player_turn():
            step = _player_auto_step(character, game_state)
            if not step:
                break
            events.append(step)
            end_msg, _ = maybe_end_combat(game_state, character)
            if end_msg:
                events.append(end_msg)
                break

        if not game_state.is_in_combat():
            break

        if game_state.combat and game_state.combat.is_player_turn():
            events.extend(end_player_turn(character, game_state))
            end_msg, _ = maybe_end_combat(game_state, character)
            if end_msg:
                events.append(end_msg)

        rounds += 1

    outcome = _summarize_outcome(character, game_state, rounds=rounds)
    if outcome == "victory":
        events.append("[自动战斗] 战斗结束：敌人已无法继续作战。")
    elif outcome == "defeat":
        events.append("[自动战斗] 战斗结束：你已倒下。")
    elif outcome == "stalemate":
        events.append("[自动战斗] 已达模拟轮次上限，战斗仍在进行。")

    return AutoCombatResult(events=events, outcome=outcome, rounds=rounds)
