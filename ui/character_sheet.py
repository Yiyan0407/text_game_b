import streamlit as st

from game.models import ABILITY_ORDER, Character


def render_character_sheet(character: Character) -> None:
    st.subheader("角色卡")
    st.markdown(f"**{character.name}**")
    st.caption(character.background)
    st.divider()

    row1 = st.columns(3)
    row2 = st.columns(3)
    for col, (key, field, label) in zip(
        (*row1, *row2),
        ABILITY_ORDER,
    ):
        value = getattr(character, field)
        mod = character.modifier(key)
        col.metric(f"{label} {key.upper()}", value, delta=f"{mod:+d}", delta_color="off")

    st.progress(character.hp / character.max_hp, text=f"HP {character.hp}/{character.max_hp}")

    if character.inventory:
        with st.expander("背包", expanded=False):
            for item in character.inventory:
                st.markdown(f"- **{item.name}**　×{item.quantity}{item.unit}")
                if item.description:
                    st.caption(item.description)
    else:
        with st.expander("背包", expanded=False):
            st.caption("空空如也——物品会在冒险中获得")

    if character.skills:
        with st.expander("技能", expanded=False):
            for skill in character.skills:
                st.markdown(f"- **{skill.name}**")
                if skill.description:
                    st.caption(skill.description)
    else:
        with st.expander("技能", expanded=False):
            st.caption(
                "开局会根据角色背景同步基础技能。"
                "冒险中可向 NPC 请教（如「向某某学潜行」）、完成训练检定后习得，"
                "或由 KP 在任务奖励时授予。"
            )
