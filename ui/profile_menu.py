import streamlit as st

from game.profile import ProfileManager, PlayerProfile
from ui.form_drafts import (
    clear_new_profile_draft,
    init_new_profile_draft,
    sync_new_profile_draft_to_disk,
)
from ui.risky_action import render_delete_confirm_dialog


def sync_profile_context() -> None:
    profile_manager: ProfileManager = st.session_state.profile_manager
    profile_id = st.session_state.get("current_profile_id")
    if not profile_id:
        return
    st.session_state.save_manager = profile_manager.get_save_manager(profile_id)
    try:
        st.session_state.current_profile = profile_manager.load_profile(profile_id)
    except FileNotFoundError:
        st.session_state.current_profile_id = None
        st.session_state.current_profile = None


def render_profile_selection(profile_manager: ProfileManager) -> None:
    st.title("👤 选择玩家档案")
    st.markdown(
        "每位玩家有独立档案，存档与角色卡互不干扰。"
        "你和朋友的进度可以分开管理。"
    )

    profiles = profile_manager.list_profiles()
    if not profiles and not st.session_state.get("legacy_migrated"):
        with st.spinner("正在迁移旧版存档……"):
            migrated = profile_manager.migrate_legacy_saves()
        if migrated:
            st.session_state.legacy_migrated = True
            profiles = profile_manager.list_profiles()
            st.info(f"已将旧版存档迁移到「{migrated.name}」。")

    if profiles:
        st.subheader("已有档案")
        for profile in profiles:
            with st.container(border=True):
                st.markdown(f"**{profile.name}**")
                cards = profile_manager.list_character_cards(profile.profile_id)
                saves = profile_manager.get_save_manager(profile.profile_id).list_saves()
                st.caption(f"角色卡 {len(cards)} · 存档 {len(saves)}")
                if st.button(
                    "进入",
                    key=f"enter_profile_{profile.profile_id}",
                    use_container_width=True,
                    type="primary",
                ):
                    select_profile(profile)
                if st.button(
                    "删除档案",
                    key=f"delete_profile_{profile.profile_id}",
                    use_container_width=True,
                ):
                    st.session_state.confirm_delete_profile_id = profile.profile_id
                    st.session_state.confirm_delete_profile_name = profile.name
                    st.rerun()

    confirm_id = st.session_state.get("confirm_delete_profile_id")
    if confirm_id:
        confirm_name = st.session_state.get("confirm_delete_profile_name", "该档案")

        def _delete_profile() -> None:
            with st.spinner("正在删除档案……"):
                profile_manager.delete_profile(confirm_id)
            if st.session_state.get("current_profile_id") == confirm_id:
                st.session_state.current_profile_id = None
                st.session_state.current_profile = None
            st.session_state.pop("confirm_delete_profile_id", None)
            st.session_state.pop("confirm_delete_profile_name", None)
            st.rerun()

        def _cancel_profile_delete() -> None:
            st.session_state.pop("confirm_delete_profile_id", None)
            st.session_state.pop("confirm_delete_profile_name", None)
            st.rerun()

        render_delete_confirm_dialog(
            title="确认删除档案",
            message=(
                f"确定删除档案「{confirm_name}」？"
                "将永久删除其下所有角色卡与存档，且无法恢复。"
            ),
            on_confirm=_delete_profile,
            on_cancel=_cancel_profile_delete,
            dialog_key=f"delete_profile_{confirm_id}",
        )

    st.divider()
    st.subheader("新建档案")
    init_new_profile_draft()
    name = st.text_input(
        "档案名称",
        placeholder="例如：小明、朋友 A",
        key="new_profile_name",
    )
    sync_new_profile_draft_to_disk()
    if st.button("创建并进入", type="primary", use_container_width=True):
        if not name.strip():
            st.error("请填写档案名称。")
            return
        profile = profile_manager.create_profile(name.strip())
        clear_new_profile_draft()
        select_profile(profile)


def select_profile(profile: PlayerProfile) -> None:
    st.session_state.current_profile_id = profile.profile_id
    st.session_state.current_profile = profile
    sync_profile_context()
    st.session_state.page = "menu"
    st.rerun()


def render_profile_switcher(profile_manager: ProfileManager) -> None:
    profile: PlayerProfile | None = st.session_state.get("current_profile")
    if not profile:
        return

    st.caption(f"当前档案：**{profile.name}**")
    c1, c2 = st.columns(2)
    if c1.button("切换档案", use_container_width=True):
        st.session_state.game_started = False
        st.session_state.page = "select_profile"
        st.rerun()
    if c2.button("角色库", use_container_width=True):
        st.session_state.page = "character_library"
        st.rerun()
