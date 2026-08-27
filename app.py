import streamlit as st

from config.settings import get_settings
from game.models import Character, ChatMessage, GameState
from game.orchestrator import GameOrchestrator
from game.profile import ProfileManager
from game.save import SaveManager
from game.scenario import Scenario
from game.session import append_tool_events, persist_save, sync_character_card_to_library
from ui.character_sheet import render_character_sheet
from ui.chat import render_chat_history, render_chat_input, render_tool_events_live
from ui.game_state_panel import render_game_state_panel
from ui.combat_panel import render_combat_panel
from ui.action_suggestions import render_action_suggestions
from ui.streaming import render_streaming_markdown
from ui.main_menu import (
    load_save_into_session,
    render_character_creation,
    render_load_save,
    render_main_menu,
    render_scenario_selection,
)
from ui.character_library import render_character_library, render_character_selection
from ui.profile_menu import render_profile_selection, sync_profile_context
from ui.scenario_generator import render_scenario_generator, render_scenario_preview
from ui.auth import render_login_gate

st.set_page_config(page_title="AI 跑团", page_icon="🎲", layout="wide")


def init_session_state() -> None:
    defaults = {
        "authenticated": False,
        "page": "menu",
        "game_started": False,
        "character": None,
        "game_state": GameState(),
        "scenario": None,
        "messages": [],
        "action_suggestions": [],
        "current_save_id": None,
        "current_profile_id": None,
        "current_profile": None,
        "current_character_id": None,
        "selected_character_card": None,
        "legacy_migrated": False,
        "orchestrator": GameOrchestrator(),
        "profile_manager": ProfileManager(),
        "save_manager": SaveManager(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def handle_player_message(user_input: str) -> None:
    character: Character = st.session_state.character
    game_state: GameState = st.session_state.game_state
    scenario: Scenario = st.session_state.scenario
    orchestrator: GameOrchestrator = st.session_state.orchestrator
    settings = get_settings()

    st.session_state.messages.append(
        ChatMessage(role="user", content=user_input)
    )

    history = st.session_state.messages[:-1]
    summary_before = game_state.story_summary

    if settings.enable_streaming:
        rejection_turn, pre_tool_events, text_stream, finish = orchestrator.player_turn_stream(
            character=character,
            game_state=game_state,
            scenario=scenario,
            user_input=user_input,
            history=history,
        )
        if rejection_turn is not None:
            st.session_state.messages.append(
                ChatMessage(
                    role="system",
                    content=(
                        f"⚠️ 行动无法执行：{rejection_turn.rejection_reason}。"
                        "请重新描述你的行动。"
                    ),
                )
            )
            return

        append_tool_events(pre_tool_events)
        render_tool_events_live(pre_tool_events)

        with st.chat_message("assistant"):
            full_response = render_streaming_markdown(text_stream)
        turn = finish(full_response or "")
    else:
        with st.spinner("KP 思考中……"):
            turn = orchestrator.player_turn(
                character=character,
                game_state=game_state,
                scenario=scenario,
                user_input=user_input,
                history=history,
            )
        if not turn.rejected:
            append_tool_events(turn.tool_events)
            st.session_state.messages.append(
                ChatMessage(role="assistant", content=turn.response)
            )
        full_response = turn.response

    if turn.rejected:
        st.session_state.messages.append(
            ChatMessage(
                role="system",
                content=(
                    f"⚠️ 行动无法执行：{turn.rejection_reason}。"
                    "请重新描述你的行动。"
                ),
            )
        )
        return

    if game_state.story_summary != summary_before:
        turn.summary_updated = True

    if settings.enable_streaming:
        kp_tool_events = [
            event
            for event in turn.tool_events
            if event not in pre_tool_events
        ]
        append_tool_events(kp_tool_events)
        st.session_state.messages.append(
            ChatMessage(role="assistant", content=full_response or turn.response)
        )

    st.session_state.action_suggestions = turn.action_suggestions
    persist_save()


def _render_scene_image(game_state: GameState, scenario: Scenario) -> None:
    settings = get_settings()
    if game_state.scene_image_url:
        st.image(game_state.scene_image_url, caption=game_state.current_scene)

    if not settings.enable_scene_images:
        return

    if st.button("🖼️ 生成场景图", use_container_width=True):
        from chain.scene_image import generate_scene_image

        with st.spinner("绘制场景中……"):
            url = generate_scene_image(
                game_state.current_scene,
                scenario.world,
                scenario.tone,
            )
        if url:
            game_state.scene_image_url = url
            persist_save()
            st.rerun()
        else:
            provider = get_settings().image_provider
            if provider == "seedream":
                st.error("场景图生成失败，请检查 SEEDREAM_API_KEY 与 SEEDREAM_MODEL。")
            else:
                st.error("场景图生成失败，请检查 OPENAI_API_KEY 配置。")


def render_gameplay_hint(game_state: GameState) -> None:
    if game_state.turn_count <= 3:
        prefix = "刚进入新模组，" if game_state.turn_count == 0 else ""
        st.info(
            f"**玩法提示**：{prefix}在下方输入你想做的事（如「观察周围」「和 NPC 交谈」）。"
            "KP 会描述结果并自动掷骰；也可以直接点击 **💡 行动建议** 按钮快速开始。"
        )


def render_game() -> None:
    character: Character = st.session_state.character
    game_state: GameState = st.session_state.game_state
    scenario: Scenario = st.session_state.scenario

    with st.sidebar:
        render_character_sheet(character)
        render_combat_panel(game_state)
        st.divider()
        render_game_state_panel(game_state)
        st.divider()
        _render_scene_image(game_state, scenario)
        st.divider()
        st.caption(f"📍 {game_state.current_scene}")
        if st.session_state.get("current_character_id"):
            st.caption("长期角色：进度会自动同步到角色卡")
        if st.button("💾 保存游戏", use_container_width=True):
            persist_save()
            st.success("已保存")
        if st.button("返回主菜单", use_container_width=True):
            persist_save()
            sync_character_card_to_library(finalize=True)
            st.session_state.game_started = False
            st.session_state.page = "menu"
            st.rerun()
        if st.button("重新开始", use_container_width=True):
            preserved = {
                key: st.session_state.get(key)
                for key in (
                    "authenticated",
                    "current_profile_id",
                    "current_profile",
                    "profile_manager",
                    "legacy_migrated",
                )
            }
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            for key, value in preserved.items():
                if value is not None:
                    st.session_state[key] = value
            init_session_state()
            sync_profile_context()
            st.session_state.page = "menu"
            st.rerun()

    st.title(f"🎲 {scenario.title}")
    render_gameplay_hint(game_state)
    render_chat_history(st.session_state.messages)

    suggested = render_action_suggestions(st.session_state.get("action_suggestions", []))
    if suggested:
        handle_player_message(suggested)
        st.rerun()

    user_input = render_chat_input(
        disabled=not get_settings().openai_api_key,
        placeholder=(
            "攻击 [敌人] / 推撞 / 交涉 / 使用药水 / 结束回合……"
            if game_state.is_in_combat()
            else None
        ),
    )
    if user_input:
        handle_player_message(user_input.strip())
        st.rerun()


def main() -> None:
    init_session_state()

    if not st.session_state.get("authenticated"):
        render_login_gate()
        return

    profile_manager: ProfileManager = st.session_state.profile_manager
    page = st.session_state.page

    if not st.session_state.get("current_profile_id") and page != "select_profile":
        st.session_state.page = "select_profile"
        page = "select_profile"

    if st.session_state.get("current_profile_id"):
        sync_profile_context()

    save_manager: SaveManager = st.session_state.save_manager

    if page == "select_profile":
        render_profile_selection(profile_manager)
    elif page == "menu":
        render_main_menu(save_manager)
    elif page == "select_scenario":
        render_scenario_selection()
    elif page == "select_character":
        render_character_selection(st.session_state.selected_scenario)
    elif page == "character_library":
        render_character_library(profile_manager)
    elif page == "character":
        render_character_creation(st.session_state.selected_scenario, creating_new_card=True)
    elif page == "load_save":
        render_load_save(save_manager)
    elif page == "generate_scenario":
        render_scenario_generator()
    elif page == "preview_scenario":
        render_scenario_preview()
    elif page == "game" and st.session_state.game_started:
        render_game()
    else:
        st.session_state.page = "menu"
        st.rerun()


if __name__ == "__main__":
    main()
