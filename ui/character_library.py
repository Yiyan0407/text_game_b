import streamlit as st

from config.worlds import WORLD_OPTIONS
from game.models import ABILITY_ORDER
from game.profile import CharacterCard, ProfileManager
from ui.character_loadout import (
    maybe_open_loadout_dialog,
    queue_loadout,
)
from ui.character_portrait import render_portrait, render_portrait_actions
from ui.risky_action import render_delete_confirm_dialog

CHARACTER_DETAIL_CARD_KEY = "character_detail_card_id"


def _has_dialog() -> bool:
    return hasattr(st, "dialog")


def _ability_summary(card: CharacterCard) -> str:
    return " · ".join(
        f"{key.upper()}{getattr(card, field)}"
        for key, field, _ in ABILITY_ORDER
    )


def _card_meta_line(card: CharacterCard, *, save_count: int | None = None) -> str:
    parts: list[str] = []
    if card.skills:
        parts.append(f"库·技能 {len(card.skills)}")
    if card.inventory:
        parts.append(f"库·物品 {len(card.inventory)}")
    if card.campaign_history:
        parts.append(f"战役 {len(card.campaign_history)}")
    if save_count is not None and save_count > 0:
        parts.append(f"存档 {save_count}")
    if card.preferred_world_id:
        world_label = WORLD_OPTIONS.get(card.preferred_world_id, card.preferred_world_id)
        parts.append(f"偏好 {world_label}")
    return " · ".join(parts) if parts else "尚无战役履历"


def _render_card_compact(
    card: CharacterCard,
    *,
    save_count: int | None = None,
    profile_manager: ProfileManager | None = None,
    profile_id: str = "",
) -> None:
    if profile_manager and profile_id:
        left, right = st.columns([1, 3])
        with left:
            render_portrait(
                profile_manager,
                profile_id,
                card,
                width=96,
                show_caption=False,
            )
        with right:
            st.markdown(f"**{card.name}**")
            background = card.background.strip()
            if len(background) > 72:
                background = background[:69] + "…"
            if background:
                st.caption(background)
            st.caption(_ability_summary(card))
            st.caption(_card_meta_line(card, save_count=save_count))
            if card.deceased:
                note = card.death_note.strip() or "永久死亡"
                st.caption(f"💀 已死亡 · {note[:48]}{'…' if len(note) > 48 else ''}")
        return

    st.markdown(f"**{card.name}**")
    background = card.background.strip()
    if len(background) > 72:
        background = background[:69] + "…"
    if background:
        st.caption(background)
    st.caption(_ability_summary(card))
    st.caption(_card_meta_line(card, save_count=save_count))
    if card.deceased:
        note = card.death_note.strip() or "永久死亡"
        st.caption(f"💀 已死亡 · {note[:48]}{'…' if len(note) > 48 else ''}")


def _render_card_stats(card: CharacterCard) -> None:
    st.markdown(f"**{card.name}**")
    st.caption(card.background)
    appearance_text = card.appearance.format_for_prompt()
    if appearance_text:
        st.caption(f"外貌：{appearance_text}")
    row1 = st.columns(3)
    row2 = st.columns(3)
    for col, (key, field, label) in zip((*row1, *row2), ABILITY_ORDER):
        value = getattr(card, field)
        mod = (value - 10) // 2
        col.metric(f"{label} {key.upper()}", value, delta=f"{mod:+d}", delta_color="off")
    if card.preferred_world_id:
        world_label = WORLD_OPTIONS.get(card.preferred_world_id, card.preferred_world_id)
        st.caption(f"偏好世界观：{world_label}")


def _render_card_career(card: CharacterCard, *, history_limit: int | None = 3) -> None:
    if card.skills:
        st.markdown("**技能**")
        for skill in card.skills:
            st.markdown(f"- {skill.format_detail()}")
    if card.equipment:
        st.markdown("**装备**")
        for entry in card.equipment:
            st.markdown(f"- {entry.slot}：{entry.item_name}")
    if card.inventory:
        st.markdown("**背包**")
        for item in card.inventory:
            st.markdown(f"- {item.format_detail()}")
    if card.campaign_history:
        st.markdown("**战役履历**")
        records = card.campaign_history
        if history_limit is not None:
            records = records[-history_limit:]
        for record in records:
            status_label = {
                "active": "进行中",
                "paused": "暂停",
                "completed": "已完成",
                "failed": "阵亡",
            }.get(record.status, record.status)
            summary = record.summary.strip() or "（尚无摘要）"
            st.caption(
                f"· 《{record.scenario_title}》[{status_label}·{record.turn_count}回合] {summary}"
            )
    elif card.career_summary.strip():
        st.caption(card.career_summary.strip())
    if card.notable_facts:
        st.markdown("**关键记忆**")
        for fact in card.notable_facts[-8:]:
            st.caption(f"· {fact}")


def _render_card_detail_body(
    card: CharacterCard,
    *,
    profile_manager: ProfileManager | None = None,
    profile_id: str = "",
) -> None:
    if profile_manager and profile_id:
        portrait_col, info_col = st.columns([1, 2])
        with portrait_col:
            render_portrait_actions(
                profile_manager,
                profile_id,
                card,
                key_prefix="detail",
            )
        with info_col:
            if card.deceased:
                note = card.death_note.strip() or "该角色已在冒险中永久死亡。"
                st.error(f"💀 已死亡 · {note}")
            _render_card_stats(card)
    else:
        if card.deceased:
            note = card.death_note.strip() or "该角色已在冒险中永久死亡。"
            st.error(f"💀 已死亡 · {note}")
        _render_card_stats(card)
    st.divider()
    _render_card_career(card, history_limit=None)


def _open_character_detail_dialog(
    card: CharacterCard,
    *,
    profile_manager: ProfileManager | None = None,
    profile_id: str = "",
) -> None:
    title = f"角色详情 · {card.name}"

    def _body() -> None:
        _render_card_detail_body(
            card,
            profile_manager=profile_manager,
            profile_id=profile_id,
        )
        if st.button("关闭", key=f"close_detail_{card.card_id}", use_container_width=True):
            st.session_state.pop(CHARACTER_DETAIL_CARD_KEY, None)
            st.rerun()

    if _has_dialog():
        @st.dialog(title, width="large")
        def _dialog_body() -> None:
            _body()

        _dialog_body()
    else:
        with st.container(border=True):
            st.subheader(title)
            _body()


def _maybe_open_character_detail_dialog(
    cards: list[CharacterCard],
    *,
    profile_manager: ProfileManager | None = None,
    profile_id: str = "",
) -> None:
    detail_id = st.session_state.get(CHARACTER_DETAIL_CARD_KEY)
    if not detail_id:
        return
    card = next((item for item in cards if item.card_id == detail_id), None)
    if card is None and profile_manager and profile_id:
        try:
            card = profile_manager.load_character_card(profile_id, detail_id)
        except FileNotFoundError:
            card = None
    if card is None:
        st.session_state.pop(CHARACTER_DETAIL_CARD_KEY, None)
        return
    _open_character_detail_dialog(
        card,
        profile_manager=profile_manager,
        profile_id=profile_id,
    )


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

        def _delete_card() -> None:
            with st.spinner("正在删除角色与存档……"):
                save_manager = profile_manager.get_save_manager(profile_id)
                deleted_ids = save_manager.list_save_ids_for_character(confirm_card.card_id)
                profile_manager.delete_character_card(profile_id, confirm_card.card_id)
                _clear_active_game_if_deleted_card(confirm_card.card_id, deleted_ids)
            st.session_state.pop("confirm_delete_card", None)
            st.session_state.pop("confirm_delete_save_count", None)
            st.rerun()

        def _cancel_card_delete() -> None:
            st.session_state.pop("confirm_delete_card", None)
            st.session_state.pop("confirm_delete_save_count", None)
            st.rerun()

        render_delete_confirm_dialog(
            title="确认删除角色",
            message=(
                f"确定删除角色「{confirm_card.name}」？"
                f"将永久删除角色卡及关联的 **{save_count}** 个存档。"
            ),
            on_confirm=_delete_card,
            on_cancel=_cancel_card_delete,
            dialog_key=f"delete_card_{confirm_card.card_id}",
        )

    cards = profile_manager.list_character_cards(profile_id)
    _maybe_open_character_detail_dialog(
        cards,
        profile_manager=profile_manager,
        profile_id=profile_id,
    )

    if not cards:
        st.info("还没有角色卡。开始新游戏并创建角色后，会自动保存到这里。")
    else:
        for card in cards:
            save_count = profile_manager.count_saves_for_character(profile_id, card.card_id)
            with st.container(border=True):
                _render_card_compact(
                    card,
                    save_count=save_count,
                    profile_manager=profile_manager,
                    profile_id=profile_id,
                )
                if save_count > 1:
                    st.caption("⚠️ 该角色有多条存档，继续冒险时请按保存时间选择正确进度。")
                c1, c2, c3 = st.columns(3)
                if c1.button(
                    "查看详情",
                    key=f"lib_detail_{card.card_id}",
                    use_container_width=True,
                ):
                    st.session_state[CHARACTER_DETAIL_CARD_KEY] = card.card_id
                    st.rerun()
                if card.deceased:
                    c2.caption("已故，不可开新局")
                elif c2.button(
                    "用此角色开新模组",
                    key=f"use_card_{card.card_id}",
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state.selected_character_card = card
                    st.session_state.page = "select_scenario"
                    st.rerun()
                if c3.button(
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
        _maybe_open_character_detail_dialog(
            cards,
            profile_manager=profile_manager,
            profile_id=profile_id,
        )

        def _start_with_loadout(card: CharacterCard, loadout) -> None:
            from ui.main_menu import start_new_game_with_card

            start_new_game_with_card(scenario, card, game_config=game_config, loadout=loadout)

        maybe_open_loadout_dialog(
            cards,
            scenario,
            game_config=game_config,
            on_confirm=_start_with_loadout,
        )

        for card in cards:
            with st.container(border=True):
                _render_card_compact(
                    card,
                    profile_manager=profile_manager,
                    profile_id=profile_id,
                )
                c1, c2 = st.columns(2)
                if c1.button(
                    "查看详情",
                    key=f"pick_detail_{card.card_id}",
                    use_container_width=True,
                ):
                    st.session_state[CHARACTER_DETAIL_CARD_KEY] = card.card_id
                    st.rerun()
                if card.deceased:
                    c2.caption("已死亡，不可选")
                elif c2.button(
                    "选择此角色",
                    key=f"pick_card_{card.card_id}",
                    use_container_width=True,
                    type="primary",
                ):
                    queue_loadout(card, scenario)
                    st.rerun()

    st.divider()
    st.subheader("创建新角色")
    render_character_creation(scenario, creating_new_card=True, game_config=game_config)

    if st.button("返回选模组", use_container_width=True):
        st.session_state.page = "select_scenario"
        st.rerun()
