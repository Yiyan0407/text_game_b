from datetime import datetime, timezone

import streamlit as st

from config.worlds import DEFAULT_WORLD_ID, WORLD_OPTIONS
from game.save import SaveManager
from game.scenario import Scenario
from game.scenario_loader import list_scenarios
from ui.streaming import render_streaming_markdown


def _format_saved_at(saved_at: str) -> str:
    try:
        dt = datetime.fromisoformat(saved_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone()
        return local.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return saved_at


def render_main_menu(save_manager: SaveManager) -> None:
    st.title("🎲 AI 跑团")
    st.markdown("选择继续冒险，或开始新的模组。")

    saves = save_manager.list_saves()
    col1, col2, col3 = st.columns(3)
    if col1.button("🆕 新游戏", use_container_width=True, type="primary"):
        st.session_state.page = "select_scenario"
        st.rerun()

    if col2.button("✨ AI 生成剧本", use_container_width=True):
        st.session_state.page = "generate_scenario"
        st.rerun()

    if saves and col3.button("📂 继续冒险", use_container_width=True):
        st.session_state.page = "load_save"
        st.rerun()

    if saves:
        st.divider()
        st.subheader("最近存档")
        for meta in saves[:3]:
            c1, c2 = st.columns([5, 1])
            if c1.button(
                f"**{meta.character_name}** · {meta.scenario_title} · 回合 {meta.turn_count}",
                key=f"quick_load_{meta.save_id}",
                use_container_width=True,
            ):
                load_save_into_session(save_manager, meta.save_id)
                st.rerun()
            if c2.button("🗑️", key=f"quick_del_{meta.save_id}", help="删除存档"):
                save_manager.delete(meta.save_id)
                st.rerun()
            st.caption(f"📍 {meta.current_scene} · {_format_saved_at(meta.saved_at)}")


def render_load_save(save_manager: SaveManager) -> None:
    st.title("📂 继续冒险")
    saves = save_manager.list_saves()

    if not saves:
        st.info("暂无存档。")
        if st.button("返回主菜单"):
            st.session_state.page = "menu"
            st.rerun()
        return

    for meta in saves:
        with st.container(border=True):
            st.markdown(f"**{meta.character_name}** — {meta.scenario_title}")
            st.caption(
                f"回合 {meta.turn_count} · 📍 {meta.current_scene} · "
                f"{_format_saved_at(meta.saved_at)}"
            )
            c1, c2 = st.columns(2)
            if c1.button("读取", key=f"load_{meta.save_id}", use_container_width=True):
                load_save_into_session(save_manager, meta.save_id)
                st.rerun()
            if c2.button("删除", key=f"del_{meta.save_id}", use_container_width=True):
                save_manager.delete(meta.save_id)
                st.rerun()

    if st.button("返回主菜单"):
        st.session_state.page = "menu"
        st.rerun()


def render_scenario_selection() -> None:
    st.title("🆕 选择模组")
    scenarios = list_scenarios()

    if not scenarios:
        st.error("未找到模组文件，请检查 data/scenarios/ 目录。")
        if st.button("返回主菜单"):
            st.session_state.page = "menu"
            st.rerun()
        return

    for scenario in scenarios:
        with st.container(border=True):
            world_label = WORLD_OPTIONS.get(scenario.world_id, scenario.world_id)
            tag = " · ✨ AI生成" if scenario.is_generated else ""
            st.markdown(f"**{scenario.title}**")
            st.caption(f"{scenario.description} · 🌍 {world_label}{tag}")
            if st.button("选择", key=f"scenario_{scenario.id}", use_container_width=True):
                st.session_state.selected_scenario = scenario
                st.session_state.page = "character"
                st.rerun()

    st.divider()
    if st.button("✨ AI 生成新剧本", use_container_width=True, type="primary"):
        st.session_state.page = "generate_scenario"
        st.rerun()

    if st.button("返回主菜单"):
        st.session_state.page = "menu"
        st.rerun()


def render_character_creation(scenario: Scenario) -> None:
    from config.settings import get_settings
    from game.character_creation import build_character, roll_ability_scores

    st.title(f"🎲 {scenario.title}")
    st.markdown(scenario.description)

    settings = get_settings()
    if not settings.openai_api_key:
        st.warning("请先在项目根目录配置 `.env` 文件中的 `OPENAI_API_KEY`。")

    default_world = (
        scenario.world_id
        if scenario.world_id in WORLD_OPTIONS
        else DEFAULT_WORLD_ID
    )

    if "rolled_abilities" not in st.session_state:
        st.session_state.rolled_abilities = roll_ability_scores()

    rolled = st.session_state.rolled_abilities

    st.subheader("属性掷骰")
    st.caption("每项属性均为 4d6 去掉最低一颗（经典创角规则），点数不可手动调整。")

    row1 = st.columns(3)
    row2 = st.columns(3)
    for col, detail in zip((*row1, *row2), rolled.details):
        mod = (detail.score - 10) // 2
        col.metric(
            f"{detail.label} {detail.key.upper()}",
            detail.score,
            delta=f"{mod:+d}",
            delta_color="off",
        )

    with st.expander("查看掷骰明细"):
        for detail in rolled.details:
            rolls_text = ", ".join(str(v) for v in detail.rolls)
            st.markdown(
                f"- **{detail.label}** {detail.score}："
                f"[{rolls_text}]，去掉 {detail.dropped}"
            )

    con_score = rolled.to_character_fields()["constitution"]
    preview_hp = max(8, 10 + (con_score - 10) // 2)
    st.info(f"根据体质 CON，初始 HP 为 **{preview_hp}**（10 + 体质修正，最低 8）")

    if st.button("🎲 重新掷骰", use_container_width=True):
        st.session_state.rolled_abilities = roll_ability_scores()
        st.rerun()

    with st.form("character_form"):
        selected_world = st.selectbox(
            "规则/世界观包",
            options=list(WORLD_OPTIONS.keys()),
            format_func=lambda k: WORLD_OPTIONS[k],
            index=list(WORLD_OPTIONS.keys()).index(default_world),
        )
        name = st.text_input("角色姓名", placeholder="例如：艾拉")
        background = st.text_area(
            "角色背景",
            placeholder="例如：前海军斥候，为还债来到灰港做佣兵。",
            height=100,
        )
        submitted = st.form_submit_button("开始冒险", type="primary", use_container_width=True)

    if submitted:
        if not name.strip():
            st.error("请填写角色姓名。")
            return
        if not settings.openai_api_key:
            st.error("缺少 OPENAI_API_KEY，无法启动游戏。")
            return

        character = build_character(
            name=name.strip(),
            background=background.strip() or "一位初到灰港的冒险者。",
            rolled=rolled,
        )
        active_scenario = scenario.model_copy(update={"world_id": selected_world})
        st.session_state.pop("rolled_abilities", None)
        start_new_game(active_scenario, character)

    if st.button("返回", key="back_from_character"):
        if st.session_state.get("generated_scenario"):
            st.session_state.page = "preview_scenario"
        else:
            st.session_state.page = "select_scenario"
        st.rerun()


def start_new_game(scenario: Scenario, character) -> None:
    from config.settings import get_settings
    from game.models import ChatMessage, GameState
    from game.save import SaveGame
    from game.session import persist_save

    game_state = GameState()
    orchestrator = st.session_state.orchestrator
    settings = get_settings()

    save_game = SaveGame.create(
        scenario_id=scenario.id,
        scenario_title=scenario.title,
        character=character,
        game_state=game_state,
        messages=[],
    )

    st.session_state.character = character
    st.session_state.game_state = game_state
    st.session_state.scenario = scenario
    st.session_state.current_save_id = save_game.save_id
    st.session_state.messages = []
    st.session_state.action_suggestions = []
    st.session_state.game_started = True
    st.session_state.page = "game"

    if settings.enable_streaming:
        tool_events, text_stream, finish = orchestrator.start_game_stream(
            character, game_state, scenario
        )
        tools_appended = False

        def _flush_tools() -> None:
            nonlocal tools_appended
            if tools_appended or not tool_events:
                return
            for event in tool_events:
                st.session_state.messages.append(
                    ChatMessage(role="system", content=f"🎲 {event}")
                )
            tools_appended = True

        with st.chat_message("assistant"):
            full = render_streaming_markdown(text_stream, on_tools_ready=_flush_tools)
        turn = finish(full or "")
        st.session_state.messages.append(
            ChatMessage(role="assistant", content=full or turn.response)
        )
        st.session_state.action_suggestions = turn.action_suggestions
    else:
        with st.spinner("KP 正在编织开场……"):
            turn = orchestrator.start_game(character, game_state, scenario)
        from game.session import append_turn_result

        append_turn_result(turn)
        st.session_state.action_suggestions = turn.action_suggestions

    persist_save()
    st.rerun()


def load_save_into_session(save_manager: SaveManager, save_id: str) -> None:
    from game.save import get_action_suggestions
    from game.scenario_loader import load_scenario

    save_game = save_manager.load(save_id)
    scenario = load_scenario(save_game.scenario_id)

    st.session_state.character = save_game.character
    st.session_state.game_state = save_game.game_state
    st.session_state.scenario = scenario
    st.session_state.messages = save_game.messages
    st.session_state.current_save_id = save_game.save_id
    st.session_state.action_suggestions = get_action_suggestions(save_game)
    st.session_state.game_started = True
    st.session_state.page = "game"
