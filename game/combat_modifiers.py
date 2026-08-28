"""战斗中的战术环境加值（烟雾、闪光等）。"""

from __future__ import annotations

from game.models import CombatState

SMOKE_COVER_ROUNDS = 2
FLASH_DISORIENT_ROUNDS = 1
SMOKE_PLAYER_CHECK_BONUS = 2
SMOKE_ENEMY_ATTACK_PENALTY = 2
SMOKE_PLAYER_AC_BONUS = 2
FLASH_ENEMY_ATTACK_PENALTY = 2
FLASH_PLAYER_CHECK_BONUS = 1


def apply_use_tag(combat: CombatState, tag: str) -> list[str]:
    normalized = tag.strip().lower()
    events: list[str] = []
    if normalized == "smoke":
        combat.smoke_cover_rounds = max(combat.smoke_cover_rounds, SMOKE_COVER_ROUNDS)
        events.append(
            f"🌫️ 烟雾遮蔽 {SMOKE_COVER_ROUNDS} 轮："
            f"你的 DEX/WIS 检定 +{SMOKE_PLAYER_CHECK_BONUS}，"
            f"AC +{SMOKE_PLAYER_AC_BONUS}，敌人对你攻击 -{SMOKE_ENEMY_ATTACK_PENALTY}"
        )
    elif normalized == "flash":
        combat.flash_disorient_rounds = max(
            combat.flash_disorient_rounds, FLASH_DISORIENT_ROUNDS
        )
        events.append(
            f"💡 强光干扰 {FLASH_DISORIENT_ROUNDS} 轮："
            f"敌人对你攻击 -{FLASH_ENEMY_ATTACK_PENALTY}，"
            f"你的 WIS/INT 检定 +{FLASH_PLAYER_CHECK_BONUS}"
        )
    return events


def tick_tactical_effects(combat: CombatState) -> None:
    if combat.smoke_cover_rounds > 0:
        combat.smoke_cover_rounds -= 1
    if combat.flash_disorient_rounds > 0:
        combat.flash_disorient_rounds -= 1


def player_ac_bonus(combat: CombatState | None) -> int:
    if combat is None:
        return 0
    bonus = 0
    if combat.smoke_cover_rounds > 0:
        bonus += SMOKE_PLAYER_AC_BONUS
    return bonus


def enemy_attack_roll_modifier(combat: CombatState | None) -> int:
    if combat is None:
        return 0
    penalty = 0
    if combat.smoke_cover_rounds > 0:
        penalty -= SMOKE_ENEMY_ATTACK_PENALTY
    if combat.flash_disorient_rounds > 0:
        penalty -= FLASH_ENEMY_ATTACK_PENALTY
    return penalty


def player_check_bonus(combat: CombatState | None, ability: str) -> int:
    if combat is None:
        return 0
    key = ability.lower()
    bonus = 0
    if combat.smoke_cover_rounds > 0 and key in ("dex", "wis"):
        bonus += SMOKE_PLAYER_CHECK_BONUS
    if combat.flash_disorient_rounds > 0 and key in ("wis", "int"):
        bonus += FLASH_PLAYER_CHECK_BONUS
    return bonus
