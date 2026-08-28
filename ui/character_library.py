import streamlit as st

from config.worlds import WORLD_OPTIONS
from game.models import ABILITY_ORDER
from game.profile import CharacterCard, ProfileManager
from ui.loading import run_with_spinner


def _render_card_stats(card: CharacterCard) -> None:
    st.markdown(f"**{card.name}**")
    st.caption(card.background)
    row1 = st.columns(3)
    row2 = st.columns(3)
    for col, (key, field, label) in zip((*row1, *row2), ABILITY_ORDER):
        value = getattr(card, field)
        mod = (value - 10) // 2
        col.metric(f"{label} {key.upper()}", value, delta=f"{mod:+d}", delta_color="off")
    if card.preferred_world_id:
        world_label = WORLD_OPTIONS.get(card.preferred_world_id, card.preferred_world_id)
        st.caption(f"偏好世界观：{world_label}")


def _render_card_career(card: CharacterCard) -> None:
    if card.skills:
        st.markdown(
            f"**技能**：{'；'.join(skill.format_detail() for skill in card.skills)}"
        )
    if card.inventory:
        st.markdown(
            f"**背包**：{'；'.join(item.format_detail() for item in card.inventory)}"
        )
    if card.campaign_history:
        st.markdown("**战役履历**")
        for record in card.campaign_history[-3:]:
            status_label = {
                "active": "进行中",
                "paused": "暂停",
                "completed": "已完成",
            }.get(record.status, record.status)
            summary = record.summary.strip() or "（尚无摘要）"
            st.caption(
                f"· 《{record.scenario_title}》[{status_label}·{record.turn_count}回合] {summary}"
            )
    elif card.career_summary.strip():
        st.caption(card.career_summary.strip())


def _clear_active_game_if_deleted_card(card_id: str, deleted_save_ids: list[str]) -> None:
    if st.session_state.get("current_character_id") == card_id:
        st.session_state.current_character_id = None
    current_save_id = st.session_state.get("current_save_id")
    if current_save_id and current_save_id in deleted_save_ids:
        st.session_state.game_started = False
        st.session_state.current_save_id = None
        st.session_state.character = None
        st.session_state.messages = []
        st.session_state.page = "menu"


def render_character_library(profile_manager: ProfileManager) -> None:
    profile_id = st.session_state.current_profile_id
    if not profile_id:
        st.session_state.page = "select_profile"
        st.rerun()
        return

    profile = st.session_state.current_profile
    st.title("📇 角色库")
    st.caption(
        f"档案：{profile.name} · 长期角色：战役摘要、技能与背包会随冒险自动同步到角色卡"
    )
    st.caption("删除角色卡将同时删除该角色的所有存档，且无法恢复。")

    confirm_card: CharacterCard | None = st.session_state.get("confirm_delete_card")
    if confirm_card:
        save_count = st.session_state.get("confirm_delete_save_count", 0)
        st.warning(
            f"确定删除角色「{confirm_card.name}」？"
            f"将永久删除角色卡及关联的 **{save_count}** 个存档。"
        )
        c1, c2 = st.columns(2)
        if c1.button("确认删除", type="primary", use_container_width=True):
            with st.spinner("正在删除角色与存档……"):
                save_manager = profile_manager.get_save_manager(profile_id)
                deleted_ids = save_manager.list_save_ids_for_character(confirm_card.card_id)
                profile_manager.delete_character_card(profile_id, confirm_card.card_id)
                _clear_active_game_if_deleted_card(confirm_card.card_id, deleted_ids)
            st.session_state.pop("confirm_delete_card", None)
            st.session_state.pop("confirm_delete_save_count", None)
            st.rerun()
        if c2.button("取消", use_container_width=True):
            st.session_state.pop("confirm_delete_card", None)
            st.session_state.pop("confirm_delete_save_count", None)
            st.rerun()
        if st.button("返回主菜单", use_container_width=True):
            st.session_state.page = "menu"
            st.rerun()
        return

    cards = profile_manager.list_character_cards(profile_id)
    if not cards:
        st.info("还没有角色卡。开始新游戏并创建角色后，会自动保存到这里。")
    else:
        for card in cards:
            with st.container(border=True):
                _render_card_stats(card)
                _render_card_career(card)
                save_count = profile_manager.count_saves_for_character(profile_id, card.card_id)
                if save_count:
                    st.caption(f"关联存档：{save_count} 个")
                    if save_count > 1:
                        st.caption(
                            "同一角色可能有多条战役存档；继续冒险时请按模组与保存时间选择正确进度。"
                        )
                c1, c2 = st.columns(2)
                if c1.button(
                    "用此角色开新模组",
                    key=f"use_card_{card.card_id}",
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state.selected_character_card = card
                    st.session_state.page = "select_scenario"
                    st.rerun()
                if c2.button(
                    "删除",
                    key=f"del_card_{card.card_id}",
                    use_container_width=True,
                ):
                    st.session_state.confirm_delete_card = card
                    st.session_state.confirm_delete_save_count = save_count
                    st.rerun()

    if st.button("返回主菜单", use_container_width=True):
        st.session_state.page = "menu"
        st.rerun()


def render_character_selection(scenario) -> None:
    from ui.main_menu import render_character_creation

    profile_manager: ProfileManager = st.session_state.profile_manager
    profile_id = st.session_state.current_profile_id
    cards = profile_manager.list_character_cards(profile_id)

    st.title(f"🎭 选择角色 · {scenario.title}")
    st.markdown("使用已有长期角色，或创建新角色。")

    from ui.game_options import render_game_options

    game_config = render_game_options(show_background_validation=True)

    if cards:
        st.subheader("已有角色卡")
        for card in cards:
            with st.container(border=True):
                _render_card_stats(card)
                _render_card_career(card)
                st.caption("开新模组时继承技能、背包与战役履历；HP 回满。")
                if st.button(
                    "选择此角色",
                    key=f"pick_card_{card.card_id}",
                    use_container_width=True,
                    type="primary",
                ):
                    from ui.main_menu import start_new_game_with_card

                    start_new_game_with_card(scenario, card, game_config=game_config)

    st.divider()
    st.subheader("创建新角色")
    render_character_creation(scenario, creating_new_card=True, game_config=game_config)

    if st.button("返回选模组", use_container_width=True):
        st.session_state.page = "select_scenario"
        st.rerun()
