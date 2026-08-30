import streamlit as st

from game.models import GameState

AUTO_COMBAT_PENDING_KEY = "auto_combat_pending"

_ACTION_GUIDE = """
**每回合资源（用完输入「结束回合」）**

| 资源 | 消耗 | 典型用途 |
|------|------|----------|
| **移动力** | 免费 | 靠近/远离敌人（`move`） |
| **免费物件互动** | 免费 · 每回合 1 次 | 拾取眼前物品、快速拔/收武器 |
| **主要动作** | 1 次 | 攻击、防御、擒抱、推撞、撤退、疾跑 |
| **附加动作** | 1 次 | 用手雷/药水、收刀威慑（`talk`） |

- 攻击已装备武器可直接打；**武器 + 武学/技能**伤害叠加。
- 敌人 **SP** = 装甲，减少每次命中扣血；打不动就换武器或跑。
"""


def _enemy_status(enemy, combat) -> str:
    dist = combat.enemy_distances.get(enemy.name)
    dist_label = f" · {dist}m" if dist is not None else ""
    sp_label = ""
    if enemy.sp_max > 0:
        sp_label = f" · SP {enemy.sp}/{enemy.sp_max}"
    elif enemy.sp > 0:
        sp_label = f" · SP {enemy.sp}"
    return f"{enemy.name} HP {enemy.hp}/{enemy.max_hp} AC {enemy.ac}{sp_label}{dist_label}"


def render_combat_panel(game_state: GameState) -> None:
    combat = game_state.combat
    if not combat or not combat.active:
        st.caption("模式：探索")
        return

    st.subheader("战斗中")
    actor = combat.current_actor()
    actor_label = "你" if actor == "player" else actor
    st.caption(f"第 {combat.round} 回合 · 先攻：{' → '.join(combat.turn_order)}")
    st.markdown(f"**当前行动者：{actor_label}**")

    with st.expander("动作说明", expanded=False):
        st.markdown(_ACTION_GUIDE)

    if combat.is_player_turn():
        st.info(
            f"轮到你了 — {combat.format_action_economy()}。"
            "可多次行动，用完后输入「结束回合」。"
        )
        main = "✓" if combat.has_main_action() else "✗"
        bonus = "✓" if combat.has_bonus_action() else "✗"
        move = "✓" if combat.has_movement() else "✗"
        free = "✓" if combat.has_free_interact() else "✗"
        st.caption(
            f"移动力 {move} ({combat.movement_remaining_m}/{combat.movement_speed_m}m) · "
            f"免费互动 {free} · 主要动作 {main} · 附加动作 {bonus}"
        )
        if st.button(
            "⚡ 自动战斗",
            key="auto_combat_button",
            use_container_width=True,
            help="系统代跑剩余战斗并结算，KP 将根据结果描写整场战斗。",
        ):
            st.session_state[AUTO_COMBAT_PENDING_KEY] = True
            st.rerun()
    else:
        st.warning(f"等待 {actor_label} 的回合（敌人行动已在后台结算）")

    for enemy in combat.enemies:
        if enemy.hp > 0:
            st.progress(
                enemy.hp / enemy.max_hp,
                text=_enemy_status(enemy, combat),
            )
        else:
            st.markdown(f"~~{enemy.name}~~ 已倒")
