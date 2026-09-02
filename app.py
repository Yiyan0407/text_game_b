import logging

import streamlit as st

from chain.llm_errors import format_llm_user_error
from config.logging_setup import setup_logging
from config.settings import get_settings
from game.game_config import default_game_config
from game.models import Character, ChatMessage, GameState
from game.orchestrator import GameOrchestrator
from game.profile import ProfileManager
from game.save import SaveManager
from game.scenario import Scenario
from game.kp_directive import is_kp_directive
from game.player_death import DEATH_REJECTION
from game.session import append_tool_events, persist_save, reload_current_save_from_disk, sync_character_card_to_library
from ui.game_visuals import render_current_scene_label, render_sidebar_visual_panel
from ui.character_sheet import render_character_sheet
from ui.chat import (
    AUTO_SEND_PROMPT_KEY,
    render_chat_history,
    render_chat_input,
    render_live_user_message,
)
from ui.game_state_panel import render_game_state_panel
from ui.combat_panel import (
    AUTO_COMBAT_PENDING_KEY,
    apply_combat_move_pending,
    render_combat_entry,
)
from ui.action_suggestions import render_action_suggestions
from ui.loading import LoadingPlaceholder, run_with_spinner
from ui.streaming import finalize_streaming_turn, render_phased_turn
from ui.game_export import render_game_pdf_download
from ui.main_menu import (
    render_character_creation,
    render_load_save,
    render_main_menu,
    render_scenario_selection,
)
from ui.character_library import render_character_library, render_character_selection
from ui.profile_menu import render_profile_selection, sync_profile_context
from ui.scenario_generator import render_scenario_generator, render_scenario_preview
from ui.auth import render_login_gate

setup_logging()

logger = logging.getLogger(__name__)

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
        "game_config": None,
        "memory_journal_open": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def handle_auto_combat(*, history: list[ChatMessage]) -> None:
    character: Character = st.session_state.character
    game_state: GameState = st.session_state.game_state
    scenario: Scenario = st.session_state.scenario
    orchestrator: GameOrchestrator = st.session_state.orchestrator
    settings = get_settings()
    game_config = st.session_state.get("game_config") or default_game_config()
    summary_before = game_state.story_summary
    user_label = "⚡ 自动战斗"
    user_msg_index = len(st.session_state.messages)
    turn_completed = False
    rollback_turn = None

    st.session_state.messages.append(ChatMessage(role="user", content=user_label))

    turn = None
    try:
        if settings.enable_streaming:
            progress = LoadingPlaceholder()
            progress.show("自动战斗中……")
            (
                rejection_turn,
                pre_tool_events,
                run_state_phase,
                text_stream,
                run_item_sync_phase,
                run_finalize_phase,
                finish_turn,
                turn_context,
                rollback_turn,
            ) = orchestrator.auto_combat_turn_stream(
                character=character,
                game_state=game_state,
                scenario=scenario,
                history=history,
                game_config=game_config,
            )
            if rejection_turn is not None and rejection_turn.rejected:
                progress.clear()
                st.session_state.messages.append(
                    ChatMessage(
                        role="system",
                        content=f"⚠️ 自动战斗无法开始：{rejection_turn.rejection_reason}",
                    )
                )
                return

            append_tool_events(pre_tool_events)
            state_events, full_response = render_phased_turn(
                pre_tool_events,
                run_state_phase,
                text_stream,
                loading=progress,
                kp_meta=False,
            )
            append_tool_events(state_events)
            turn = finalize_streaming_turn(
                full_response,
                run_item_sync_phase=run_item_sync_phase,
                run_finalize_phase=run_finalize_phase,
                finish_turn=finish_turn,
            )
            append_tool_events(
                [
                    event
                    for event in turn.tool_events
                    if event not in pre_tool_events and event not in state_events
                ]
            )
            progress.clear()
            st.session_state.messages.append(
                ChatMessage(role="assistant", content=full_response or turn.response)
            )
        else:
            with st.spinner("自动战斗中……"):
                turn = orchestrator.auto_combat_turn(
                    character=character,
                    game_state=game_state,
                    scenario=scenario,
                    history=history,
                    game_config=game_config,
                )
            if turn.rejected:
                st.session_state.messages.append(
                    ChatMessage(
                        role="system",
                        content=f"⚠️ 自动战斗无法开始：{turn.rejection_reason}",
                    )
                )
                return
            append_tool_events(turn.tool_events)
            st.session_state.messages.append(
                ChatMessage(role="assistant", content=turn.response)
            )

        if game_state.story_summary != summary_before:
            pass
        if turn is not None:
            st.session_state.action_suggestions = turn.action_suggestions
        turn_completed = True
    except Exception as exc:
        logger.exception("自动战斗处理失败")
        if rollback_turn:
            rollback_turn()
        st.session_state.messages = st.session_state.messages[:user_msg_index]
        st.session_state.messages.append(
            ChatMessage(
                role="system",
                content=f"⚠️ 自动战斗处理出错：{exc}。状态已回滚，请稍后重试。",
            )
        )
        st.error(f"自动战斗失败：{format_llm_user_error(exc)}")
    finally:
        if turn_completed and st.session_state.get("game_started") and st.session_state.get("character"):
            persist_save()


def handle_player_message(user_input: str, *, history: list[ChatMessage]) -> None:
    character: Character = st.session_state.character
    game_state: GameState = st.session_state.game_state
    scenario: Scenario = st.session_state.scenario
    orchestrator: GameOrchestrator = st.session_state.orchestrator
    settings = get_settings()
    game_config = st.session_state.get("game_config") or default_game_config()
    summary_before = game_state.story_summary
    user_msg_index = len(st.session_state.messages) - 1
    turn_completed = False
    rollback_turn = None
    item_events: list[str] = []

    try:
        kp_meta_turn = is_kp_directive(user_input)
        if not character.is_alive() and not kp_meta_turn:
            st.session_state.messages.append(
                ChatMessage(role="system", content=f"⚠️ {DEATH_REJECTION}")
            )
            return
        if settings.enable_streaming:
            progress = LoadingPlaceholder()
            progress.show("KP 沟通中……" if kp_meta_turn else "裁定行动中……")
            (
                rejection_turn,
                pre_tool_events,
                run_state_phase,
                text_stream,
                run_item_sync_phase,
                run_finalize_phase,
                finish_turn,
                turn_context,
                rollback_turn,
            ) = orchestrator.player_turn_stream(
                character=character,
                game_state=game_state,
                scenario=scenario,
                user_input=user_input,
                history=history,
                game_config=game_config,
            )
            if rejection_turn is not None:
                progress.clear()
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

            state_events, full_response = render_phased_turn(
                pre_tool_events,
                run_state_phase,
                text_stream,
                loading=progress,
                kp_meta=kp_meta_turn,
            )
            append_tool_events(state_events)
            turn = finalize_streaming_turn(
                full_response,
                run_item_sync_phase=run_item_sync_phase,
                run_finalize_phase=run_finalize_phase,
                finish_turn=finish_turn,
                kp_meta=kp_meta_turn,
            )
            item_events = [
                event
                for event in turn.tool_events
                if event not in pre_tool_events and event not in state_events
            ]
            append_tool_events(item_events)
            progress.clear()
        else:
            with st.spinner("KP 沟通中……" if kp_meta_turn else "KP 思考中……"):
                turn = orchestrator.player_turn(
                    character=character,
                    game_state=game_state,
                    scenario=scenario,
                    user_input=user_input,
                    history=history,
                    game_config=game_config,
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
                and event not in state_events
                and event not in item_events
            ]
            append_tool_events(kp_tool_events)
            st.session_state.messages.append(
                ChatMessage(role="assistant", content=full_response or turn.response)
            )

        st.session_state.action_suggestions = turn.action_suggestions
        turn_completed = True
    except Exception as exc:
        logger.exception("玩家回合处理失败")
        if rollback_turn:
            rollback_turn()
        st.session_state.messages = st.session_state.messages[: user_msg_index + 1]
        st.session_state.messages.append(
            ChatMessage(
                role="system",
                content=(
                    f"⚠️ 本轮处理出错：{exc}。"
                    "状态已回滚，请稍后重试。"
                ),
            )
        )
        st.error(f"处理失败：{format_llm_user_error(exc)}")
    finally:
        if turn_completed and st.session_state.get("game_started") and st.session_state.get("character"):
            persist_save()


def render_gameplay_hint(game_state: GameState) -> None:
    if game_state.turn_count <= 3:
        prefix = "刚进入新模组，" if game_state.turn_count == 0 else ""
        st.info(
            f"**玩法提示**：{prefix}在下方输入你想做的事（如「观察周围」「和 NPC 交谈」）。"
            "KP 会描述结果并自动掷骰；也可点击 **💡 行动建议** 快速发送，或在下方输入框自行描述。"
            "若需与主持人沟通规则问题或申请回退错误结算，以 **【kp】** 开头输入（如「【kp】刚才任务不应失败，请恢复」）。"
        )


def render_game() -> None:
    _render_sync_save_feedback()
    character: Character = st.session_state.character
    game_state: GameState = st.session_state.game_state
    scenario: Scenario = st.session_state.scenario

    with st.sidebar:
        has_portrait = render_sidebar_visual_panel(game_state=game_state, scenario=scenario)
        if has_portrait:
            st.divider()
        render_character_sheet(character, show_identity=not has_portrait)
        st.divider()
        render_game_state_panel(
            game_state,
            scenario,
            game_config=st.session_state.get("game_config"),
        )
        st.divider()
        if st.session_state.get("current_character_id"):
            st.caption("长期角色：进度会自动同步到角色卡")
        st.caption("每回合结束后自动存档")
        if st.session_state.get("last_loaded_save_at"):
            st.caption(f"存档时间：{st.session_state.last_loaded_save_at}")
        _render_sync_save_button(button_key="sync_save_sidebar")
        if st.button("💾 立即存档", use_container_width=True):
            run_with_spinner("保存中……", persist_save)
            st.success("已保存")
        render_game_pdf_download(
            scenario,
            character,
            game_state,
            st.session_state.messages,
        )
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

    title_col, sync_col = st.columns([6, 1])
    with title_col:
        st.title(f"🎲 {scenario.title}")
        render_current_scene_label(game_state)
    with sync_col:
        _render_sync_save_button(button_key="sync_save_header")

    render_gameplay_hint(game_state)
    if not character.is_alive():
        st.error(
            "角色已死亡（HP 0）。普通行动已禁用；"
            "可在下方输入 **【kp】** 与主持人沟通（如申诉、读档说明），"
            "或从主菜单 **继续冒险** 读取其他存档。"
        )
    render_chat_history(st.session_state.messages)

    if apply_combat_move_pending(character, game_state):
        st.rerun()

    render_combat_entry(game_state, character=character)
    render_action_suggestions(st.session_state.get("action_suggestions", []))

    if st.session_state.pop(AUTO_COMBAT_PENDING_KEY, False):
        history = list(st.session_state.messages)
        handle_auto_combat(history=history)
        st.rerun()

    # chat_input 须为页面最后一个组件，提交后在下方即时渲染本轮对话。
    user_input = render_chat_input(
        disabled=not get_settings().openai_api_key,
        placeholder=(
            "角色已死亡 — 仅可输入【kp】沟通，例：【kp】把 HP 恢复到 10（测试）"
            if not character.is_alive()
            else (
                "攻击 [敌人] / 推撞 / 交涉 / 使用药水 / 结束回合……"
                if game_state.is_in_combat()
                else None
            )
        ),
    )
    turn_input = st.session_state.pop(AUTO_SEND_PROMPT_KEY, None) or user_input
    if turn_input:
        turn_input = turn_input.strip()
    if turn_input:
        history = list(st.session_state.messages)
        st.session_state.messages.append(
            ChatMessage(role="user", content=turn_input)
        )
        render_live_user_message(turn_input)
        handle_player_message(turn_input, history=history)
        st.rerun()


def _render_sync_save_feedback() -> None:
    error = st.session_state.pop("sync_save_error", None)
    if error:
        st.error(error)
    feedback = st.session_state.pop("sync_save_feedback", None)
    if feedback:
        st.toast(feedback)


def _handle_sync_save_click() -> None:
    result = reload_current_save_from_disk()
    if not result.success:
        st.session_state.sync_save_error = result.error
    elif result.already_latest:
        st.session_state.sync_save_feedback = "已是最新进度"
    elif result.new_messages:
        st.session_state.sync_save_feedback = f"已同步，新增 {result.new_messages} 条记录"
    else:
        st.session_state.sync_save_feedback = f"已同步 · 回合 {result.turn_count}"
    st.rerun()


def _render_sync_save_button(*, button_key: str) -> None:
    if st.button(
        "🔄 同步最新进度",
        key=button_key,
        use_container_width=True,
        help="从磁盘重新加载当前存档。观战时用此按钮刷新页面查看最新回合，无需刷新浏览器。",
    ):
        _handle_sync_save_click()


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


def run_app() -> None:
    main()


pg = st.navigation(
    [
        st.Page(run_app, title="AI 跑团", default=True),
        st.Page(
            "pages/debug.py",
            title="Debug 日志",
            url_path="debug",
            visibility="hidden",
        ),
    ],
    position="hidden",
)
pg.run()
