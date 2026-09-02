"""开新战役前从角色库挑选携带物。"""

from __future__ import annotations

import streamlit as st

from game.profile import (
    MAX_LOADOUT_ITEMS,
    MAX_LOADOUT_SKILLS,
    CharacterCard,
    CharacterLoadout,
)
from game.scenario import Scenario

LOADOUT_CARD_KEY = "pending_loadout_card_id"
LOADOUT_SCENARIO_KEY = "pending_loadout_scenario_id"


def _has_dialog() -> bool:
    return hasattr(st, "dialog")


def _item_label(name: str, card: CharacterCard) -> str:
    for item in card.inventory:
        if item.name == name:
            return item.format_detail()
    return name


def _equipment_option_key(entry) -> str:
    return f"{entry.slot}:{entry.item_name}"


def _parse_equipment_keys(keys: list[str], card: CharacterCard) -> list:
    from game.equipment import EquipmentEntry

    picked: list[EquipmentEntry] = []
    for key in keys:
        for entry in card.equipment:
            if _equipment_option_key(entry) == key:
                picked.append(entry.model_copy())
                break
    return picked


def render_loadout_picker(
    card: CharacterCard,
    scenario: Scenario,
    *,
    game_config,
    on_confirm,
) -> None:
    """弹窗或页内表单：挑选本场携带的技能、物品与装备。"""
    st.markdown(f"**{card.name}** → 《{scenario.title}》")
    st.caption(
        f"角色库中的物品/技能会保留；未勾选的不带入本场（库中约 "
        f"{len(card.skills)} 技能 · {len(card.inventory)} 物品）。"
        f" 最多携带 {MAX_LOADOUT_SKILLS} 技能、{MAX_LOADOUT_ITEMS} 物品。"
    )

    skill_names = [skill.name for skill in card.skills]
    item_names = [item.name for item in card.inventory]

    selected_skills = st.multiselect(
        "携带技能",
        options=skill_names,
        default=[],
        max_selections=MAX_LOADOUT_SKILLS,
        key=f"loadout_skills_{card.card_id}",
    )
    selected_items = st.multiselect(
        "携带物品",
        options=item_names,
        default=[],
        format_func=lambda name: _item_label(name, card),
        max_selections=MAX_LOADOUT_ITEMS,
        key=f"loadout_items_{card.card_id}",
    )

    equip_options = [
        entry
        for entry in card.equipment
        if entry.item_name in selected_items
    ]
    equip_keys = [_equipment_option_key(entry) for entry in equip_options]
    equip_labels = {
        key: entry.format_line() for key, entry in zip(equip_keys, equip_options)
    }
    selected_equip_keys = st.multiselect(
        "穿戴装备（须先勾选对应物品）",
        options=equip_keys,
        default=equip_keys,
        format_func=lambda key: equip_labels.get(key, key),
        key=f"loadout_equip_{card.card_id}",
    )

    c1, c2 = st.columns(2)
    if c1.button("开始冒险", type="primary", use_container_width=True):
        loadout = CharacterLoadout(
            skill_names=list(selected_skills),
            item_names=list(selected_items),
            equipment=_parse_equipment_keys(selected_equip_keys, card),
        )
        on_confirm(loadout)
    if c2.button("取消", use_container_width=True):
        st.session_state.pop(LOADOUT_CARD_KEY, None)
        st.session_state.pop(LOADOUT_SCENARIO_KEY, None)
        st.rerun()


def open_loadout_dialog(
    card: CharacterCard,
    scenario: Scenario,
    *,
    game_config,
    on_confirm,
) -> None:
    title = f"挑选携带 · {card.name}"

    def _body() -> None:
        render_loadout_picker(
            card,
            scenario,
            game_config=game_config,
            on_confirm=on_confirm,
        )

    if _has_dialog():

        @st.dialog(title, width="large")
        def _dialog_body() -> None:
            _body()

        _dialog_body()
    else:
        with st.container(border=True):
            st.subheader(title)
            _body()


def queue_loadout(card: CharacterCard, scenario: Scenario) -> None:
    st.session_state[LOADOUT_CARD_KEY] = card.card_id
    st.session_state[LOADOUT_SCENARIO_KEY] = scenario.id


def maybe_open_loadout_dialog(
    cards: list[CharacterCard],
    scenario: Scenario,
    *,
    game_config,
    on_confirm,
) -> None:
    card_id = st.session_state.get(LOADOUT_CARD_KEY)
    scenario_id = st.session_state.get(LOADOUT_SCENARIO_KEY)
    if not card_id or scenario_id != scenario.id:
        return
    card = next((item for item in cards if item.card_id == card_id), None)
    if card is None:
        st.session_state.pop(LOADOUT_CARD_KEY, None)
        st.session_state.pop(LOADOUT_SCENARIO_KEY, None)
        return

    def _confirm(loadout: CharacterLoadout) -> None:
        st.session_state.pop(LOADOUT_CARD_KEY, None)
        st.session_state.pop(LOADOUT_SCENARIO_KEY, None)
        on_confirm(card, loadout)

    open_loadout_dialog(
        card,
        scenario,
        game_config=game_config,
        on_confirm=_confirm,
    )
