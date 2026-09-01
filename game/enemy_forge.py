"""开战敌人数值：按个体收集待生成目标并合并 Router / EnemyForge 结果。"""

from __future__ import annotations

from dataclasses import dataclass

from game.models import GameState
from game.results import ActionRouteResult, EnemyDefPatch
from game.text_match import resolve_fuzzy_name


@dataclass(frozen=True)
class EnemyForgeTarget:
    name: str
    description: str = ""


def is_valid_enemy_def(patch: EnemyDefPatch) -> bool:
    return bool(patch.name.strip()) and patch.hp > 0


def names_from_enemies_spec(spec: str) -> list[str]:
    names: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        name = part.split(":")[0].strip().strip("'\"")
        if name and name not in names:
            names.append(name)
    return names


def _npc_context(game_state: GameState, name: str) -> str:
    resolved = resolve_fuzzy_name(name, [npc.name for npc in game_state.npcs if npc.name.strip()])
    if not resolved:
        return ""
    for npc in game_state.npcs:
        if npc.name != resolved:
            continue
        parts: list[str] = []
        if npc.attitude:
            parts.append(f"态度={npc.attitude}")
        if npc.notes.strip():
            parts.append(npc.notes.strip())
        if npc.combat and npc.combat.max_hp > 0:
            rec = npc.combat
            parts.append(
                f"已有档案 HP {rec.hp}/{rec.max_hp} AC {rec.ac} "
                f"伤害 {rec.attack_damage or '?'}"
            )
        return "；".join(parts)
    return ""


def collect_enemy_forge_targets(
    route: ActionRouteResult,
    game_state: GameState,
) -> tuple[list[EnemyForgeTarget], list[EnemyDefPatch]]:
    """返回需 LLM 生成的目标，以及 Router 已提供的有效 defs。"""
    valid_defs = [item for item in route.enemy_defs if is_valid_enemy_def(item)]
    valid_names = [item.name for item in valid_defs]

    names = names_from_enemies_spec(route.enemies_spec)
    if not names:
        names = [
            npc.name.strip()
            for npc in game_state.npcs
            if npc.attitude == "hostile" and npc.name.strip()
        ]

    kept: list[EnemyDefPatch] = []
    targets: list[EnemyForgeTarget] = []
    for name in names:
        matched = resolve_fuzzy_name(name, valid_names)
        if matched:
            for item in valid_defs:
                if item.name == matched:
                    kept.append(item)
                    break
            continue
        targets.append(
            EnemyForgeTarget(
                name=name,
                description=_npc_context(game_state, name),
            )
        )
    return targets, kept


def merge_enemy_defs(
    kept: list[EnemyDefPatch],
    forged: list[EnemyDefPatch],
    *,
    expected_names: list[str] | None = None,
) -> list[EnemyDefPatch]:
    merged: list[EnemyDefPatch] = []
    seen: set[str] = set()
    for patch in kept + forged:
        if not is_valid_enemy_def(patch):
            continue
        key = patch.name.strip()
        if key in seen:
            continue
        seen.add(key)
        merged.append(patch)
    if expected_names:
        order = {name: index for index, name in enumerate(expected_names)}
        merged.sort(key=lambda item: order.get(item.name.strip(), len(order)))
    return merged


def format_enemy_forge_event(patch: EnemyDefPatch) -> str:
    sp_part = f" SP {patch.sp}/{patch.sp_max}" if patch.sp_max > 0 or patch.sp > 0 else ""
    return (
        f"EnemyForge·{patch.name}：HP {patch.hp} AC {patch.ac} "
        f"{patch.attack_damage}{sp_part}"
    )
