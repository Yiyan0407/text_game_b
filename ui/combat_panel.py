import streamlit as st

from game.models import GameState


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

    if combat.is_player_turn():
        st.info(
            f"轮到你了 — {combat.format_action_economy()}。"
            "可多次行动，用完后输入「结束回合」。"
        )
        main = "✓" if combat.has_main_action() else "✗"
        bonus = "✓" if combat.has_bonus_action() else "✗"
        st.caption(f"主要动作 {main} · 附加动作 {bonus}")
    else:
        st.warning(f"等待 {actor_label} 的回合（敌人行动已在后台结算）")

    for enemy in combat.enemies:
        if enemy.hp > 0:
            st.progress(
                enemy.hp / enemy.max_hp,
                text=f"{enemy.name} HP {enemy.hp}/{enemy.max_hp} AC {enemy.ac}",
            )
        else:
            st.markdown(f"~~{enemy.name}~~ 已倒")
