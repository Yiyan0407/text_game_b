import streamlit as st

from game.models import GameState


def render_combat_panel(game_state: GameState) -> None:
    combat = game_state.combat
    if not combat or not combat.active:
        return

    st.subheader("⚔️ 战斗中")
    st.caption(f"第 {combat.round} 回合 · 先攻：{' → '.join(combat.turn_order)}")

    for enemy in combat.enemies:
        if enemy.hp > 0:
            st.progress(
                enemy.hp / enemy.max_hp,
                text=f"{enemy.name} HP {enemy.hp}/{enemy.max_hp} AC {enemy.ac}",
            )
        else:
            st.markdown(f"~~{enemy.name}~~ 已倒")
