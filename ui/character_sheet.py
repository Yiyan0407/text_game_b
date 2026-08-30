import streamlit as st

from game.effect_resolver import get_effective_sp
from game.equipment import SLOT_LABELS
from game.models import ABILITY_ORDER, Character


def _effective_sp_display(character: Character) -> tuple[int, str]:
    return get_effective_sp(character)



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

    max_hp = max(1, character.effective_max_hp())
    hp_ratio = max(0.0, min(1.0, character.hp / max_hp))
    st.progress(hp_ratio, text=f"HP {character.hp}/{max_hp}")

    effective_sp, sp_source = _effective_sp_display(character)
    if effective_sp > 0:
        st.caption(f"有效 SP {effective_sp}" + (f"（{sp_source}）" if sp_source else ""))

    grouped = character.equipment_by_slot()
    has_equipment = any(grouped.get(slot) for slot in SLOT_LABELS)
    with st.expander("装备", expanded=has_equipment):
        for slot, label in SLOT_LABELS.items():
            items = grouped.get(slot, [])
            if items:
                for line in items:
                    st.markdown(f"**{label}** · {line}")
            else:
                st.caption(f"{label} · （空）")
        if not has_equipment:
            st.caption("穿戴/植入/拿在手上的物品会显示在此；卸下后才会回到背包列表。")

    unequipped = character.unequipped_inventory()
    if unequipped:
        with st.expander("背包", expanded=False):
            for item in unequipped:
                st.markdown(f"- **{item.format_full_line()}**")
    else:
        with st.expander("背包", expanded=False):
            if character.equipment:
                st.caption("已装备物品见上方装备栏；背包无额外物品。")
            else:
                st.caption("空空如也——物品会在冒险中获得")

    if character.skills:
        with st.expander("技能", expanded=False):
            for skill in character.skills:
                line = skill.name
                if skill.effects and skill.effects.format_summary():
                    line += f" · {skill.effects.format_summary()}"
                st.markdown(f"- **{line}**")
                if skill.description:
                    st.caption(skill.description)
    else:
        with st.expander("技能", expanded=False):
            st.caption(
                "开局会根据角色背景同步基础技能。"
                "冒险中可向 NPC 请教（如「向某某学潜行」）、完成训练检定后习得，"
                "或由 KP 在任务奖励时授予。"
            )
