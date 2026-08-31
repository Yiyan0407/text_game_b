"""友方战斗数值持久化：跨场战斗保留 HP/护甲/死亡状态。"""

from __future__ import annotations

from game.models import CombatAlly, GameState, NpcCombatRecord, NPCRelation
from game.npc_merge import merge_npc_notes


def record_from_ally(ally: CombatAlly) -> NpcCombatRecord:
    return NpcCombatRecord(
        hp=ally.hp,
        max_hp=ally.max_hp,
        ac=ally.ac,
        attack_damage=ally.effective_attack_damage(),
        attack_bonus=ally.attack_bonus,
        sp=ally.sp,
        sp_max=ally.sp_max,
        use_dex=ally.use_dex,
        attack_range_normal_m=ally.attack_range_normal_m,
        attack_range_max_m=ally.attack_range_max_m,
        dead=ally.hp <= 0,
    )


def apply_record_to_ally(ally: CombatAlly, record: NpcCombatRecord) -> None:
    ally.hp = max(0, record.hp)
    ally.max_hp = max(1, record.max_hp)
    ally.ac = max(1, record.ac)
    ally.attack_damage = (record.attack_damage or "1d6").strip()
    ally.damage_notation = ally.attack_damage
    ally.attack_bonus = record.attack_bonus
    ally.sp = max(0, record.sp)
    ally.sp_max = max(ally.sp, record.sp_max) if record.sp_max > 0 else ally.sp
    ally.use_dex = record.use_dex
    ally.attack_range_normal_m = max(0, record.attack_range_normal_m)
    ally.attack_range_max_m = max(0, record.attack_range_max_m)


def _ensure_npc(game_state: GameState, name: str) -> NPCRelation:
    npc = game_state.find_npc(name)
    if npc is not None:
        return npc
    game_state.upsert_npc(name, "friendly", "")
    npc = game_state.find_npc(name)
    assert npc is not None
    return npc


def init_npc_combat_record(game_state: GameState, ally: CombatAlly) -> None:
    npc = _ensure_npc(game_state, ally.name)
    npc.combat = record_from_ally(ally)


def is_ally_dead_in_world(game_state: GameState | None, name: str) -> bool:
    if game_state is None:
        return False
    npc = game_state.find_npc(name)
    return bool(npc and npc.combat and npc.combat.dead)


def sync_combat_allies_to_npcs(game_state: GameState) -> list[str]:
    """战斗结束时把友方状态写回 NPC 档案。"""
    combat = game_state.combat
    if combat is None:
        return []

    events: list[str] = []
    for ally in combat.allies:
        npc = _ensure_npc(game_state, ally.name)
        record = record_from_ally(ally)
        npc.combat = record
        if record.dead:
            events.append(f"友方 {ally.name} 已在战斗中阵亡。")
            if "阵亡" not in npc.notes:
                npc.notes = merge_npc_notes(npc.notes, "已在战斗中阵亡")
    return events


def merge_combat_records(
    left: NpcCombatRecord | None,
    right: NpcCombatRecord | None,
) -> NpcCombatRecord | None:
    if left is None:
        return right.model_copy() if right is not None else None
    if right is None:
        return left.model_copy()

    dead = left.dead or right.dead
    hp = min(left.hp, right.hp)
    max_hp = max(left.max_hp, right.max_hp)
    sp = min(left.sp, right.sp)
    sp_max = max(left.sp_max, right.sp_max)
    merged = left.model_copy()
    merged.dead = dead
    merged.hp = 0 if dead else hp
    merged.max_hp = max_hp
    merged.sp = sp
    merged.sp_max = sp_max
    merged.ac = max(left.ac, right.ac)
    if len(right.attack_damage) > len(left.attack_damage):
        merged.attack_damage = right.attack_damage
    merged.attack_bonus = max(left.attack_bonus, right.attack_bonus)
    merged.use_dex = left.use_dex or right.use_dex
    merged.attack_range_normal_m = max(
        left.attack_range_normal_m, right.attack_range_normal_m
    )
    merged.attack_range_max_m = max(left.attack_range_max_m, right.attack_range_max_m)
    return merged
