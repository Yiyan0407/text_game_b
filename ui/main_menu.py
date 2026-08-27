from datetime import datetime, timezone

import streamlit as st

from config.worlds import DEFAULT_WORLD_ID, WORLD_OPTIONS
from game.profile import CharacterCard
from game.save import SaveManager
from game.scenario import Scenario
from game.scenario_loader import list_scenarios
from ui.chat import render_tool_events_live
from ui.loading import LoadingPlaceholder, run_with_spinner
from ui.profile_menu import render_profile_switcher
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
    render_profile_switcher(st.session_state.profile_manager)
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
                ok = run_with_spinner(
                    "读取存档中……",
                    lambda save_id=meta.save_id: load_save_into_session(save_manager, save_id),
                )
                if ok:
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
                ok = run_with_spinner(
                    "读取存档中……",
                    lambda save_id=meta.save_id: load_save_into_session(save_manager, meta.save_id),
                )
                if ok:
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
                preselected = st.session_state.get("selected_character_card")
                if preselected:
                    start_new_game_with_card(scenario, preselected)
                else:
                    st.session_state.page = "select_character"
                st.rerun()

    st.divider()
    if st.button("✨ AI 生成新剧本", use_container_width=True, type="primary"):
        st.session_state.page = "generate_scenario"
        st.rerun()

    if st.button("返回主菜单"):
        st.session_state.page = "menu"
        st.rerun()


def render_character_creation(scenario: Scenario, *, creating_new_card: bool = False) -> None:
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

    total = rolled.total_score()
    prev_total = st.session_state.get("rolled_abilities_prev_total")
    total_cols = st.columns([1, 2])
    with total_cols[0]:
        st.metric(
            "属性总和",
            total,
            delta=f"{total - prev_total:+d}" if prev_total is not None else None,
            delta_color="normal",
            help="六项属性点数之和；重骰后箭头表示与上一组相比增减",
        )
    with total_cols[1]:
        st.caption("经典参考区间约 **72–78**；重骰后可看总和箭头判断高了还是低了。")

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
        st.session_state.rolled_abilities_prev_total = rolled.total_score()
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
        st.caption(
            "背景应描述身份与动机，不要写开局无敌、满级、神器或巨额资源。"
            "职业不必与模组默认开场一致，开局会自动衔接你的身份。"
        )
        submitted = st.form_submit_button("开始冒险", type="primary", use_container_width=True)

    if submitted:
        if not name.strip():
            st.error("请填写角色姓名。")
            return
        if not settings.openai_api_key:
            st.error("缺少 OPENAI_API_KEY，无法启动游戏。")
            return

        custom_background = background.strip()
        if custom_background:
            from chain.background_validator import BackgroundValidator

            with st.spinner("正在审核角色背景……"):
                bg_result = BackgroundValidator().evaluate(
                    custom_background,
                    world_id=selected_world,
                    scenario=scenario,
                )
            if not bg_result.approved:
                st.error(f"背景无法通过审核：{bg_result.rejection_reason}")
                return

        character = build_character(
            name=name.strip(),
            background=custom_background or "一位初到灰港的冒险者。",
            rolled=rolled,
        )
        active_scenario = scenario.model_copy(update={"world_id": selected_world})
        st.session_state.pop("rolled_abilities", None)
        st.session_state.pop("rolled_abilities_prev_total", None)

        saved_card = CharacterCard.from_character(
            character,
            preferred_world_id=selected_world,
        )
        with st.spinner("保存角色卡……"):
            st.session_state.profile_manager.save_character_card(
                st.session_state.current_profile_id,
                saved_card,
            )
        st.session_state.pop("selected_character_card", None)
        start_new_game(active_scenario, character, character_card=saved_card)

    if st.button("返回", key="back_from_character"):
        if st.session_state.get("generated_scenario"):
            st.session_state.page = "preview_scenario"
        elif creating_new_card:
            st.session_state.page = "select_character"
        else:
            st.session_state.page = "select_scenario"
        st.rerun()


def start_new_game_with_card(scenario: Scenario, card: CharacterCard) -> None:
    world_id = card.preferred_world_id or scenario.world_id
    active_scenario = scenario.model_copy(update={"world_id": world_id})
    character = card.to_runtime_character()
    st.session_state.pop("selected_character_card", None)
    start_new_game(active_scenario, character, character_card=card)


def start_new_game(
    scenario: Scenario,
    character,
    *,
    character_card: CharacterCard | None = None,
    career_context: str = "",
) -> None:
    from config.settings import get_settings
    from game.models import ChatMessage, GameState
    from game.save import SaveGame
    from game.profile import prepare_card_for_new_campaign
    from game.session import append_tool_events, persist_save

    game_state = GameState()
    orchestrator = st.session_state.orchestrator
    settings = get_settings()

    if character_card:
        if not career_context:
            career_context = character_card.format_career_context()
        prepare_card_for_new_campaign(character_card, scenario)
        st.session_state.profile_manager.save_character_card(
            st.session_state.current_profile_id,
            character_card,
        )

    save_game = SaveGame.create(
        scenario_id=scenario.id,
        scenario_title=scenario.title,
        character=character,
        game_state=game_state,
        messages=[],
        profile_id=st.session_state.current_profile_id or "",
        character_id=character_card.card_id if character_card else "",
        world_id=scenario.world_id,
    )

    st.session_state.character = character
    st.session_state.game_state = game_state
    st.session_state.scenario = scenario
    st.session_state.current_save_id = save_game.save_id
    st.session_state.current_character_id = character_card.card_id if character_card else None
    st.session_state.messages = []
    st.session_state.action_suggestions = []
    st.session_state.game_started = True
    st.session_state.page = "game"

    if settings.enable_streaming:
        progress = LoadingPlaceholder()
        progress.show("编织入场逻辑……")
        tool_events, pre_tool_events, state_events, text_stream, finish = (
            orchestrator.start_game_stream(
                character, game_state, scenario, career_context=career_context
            )
        )
        from game.session import append_tool_events
        from ui.streaming import render_phased_turn

        append_tool_events(pre_tool_events)
        append_tool_events(state_events)

        with st.chat_message("assistant"):
            full = render_phased_turn(
                pre_tool_events,
                state_events,
                text_stream,
                loading=progress,
            )
        with st.spinner("生成行动建议中……"):
            turn = finish(full or "")
        progress.clear()
        st.session_state.messages.append(
            ChatMessage(role="assistant", content=full or turn.response)
        )
        st.session_state.action_suggestions = turn.action_suggestions
    else:
        with st.spinner("正在生成入场逻辑并编织开场……"):
            turn = orchestrator.start_game(
                character, game_state, scenario, career_context=career_context
            )
        from game.session import append_turn_result

        append_turn_result(turn)
        st.session_state.action_suggestions = turn.action_suggestions

    persist_save()
    st.rerun()


def load_save_into_session(save_manager: SaveManager, save_id: str) -> bool:
    from game.save import get_action_suggestions
    from game.scenario_loader import ScenarioNotFoundError, load_scenario

    try:
        save_game = save_manager.load(save_id)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        st.error(f"存档读取失败：{exc}")
        return False

    try:
        scenario = load_scenario(save_game.scenario_id)
    except ScenarioNotFoundError:
        st.error(
            f"存档关联的模组「{save_game.scenario_id}」不存在，"
            "可能已被删除。请重新选择模组或恢复模组文件。"
        )
        return False

    if save_game.world_id:
        scenario = scenario.model_copy(update={"world_id": save_game.world_id})

    st.session_state.character = save_game.character
    st.session_state.game_state = save_game.game_state
    st.session_state.scenario = scenario
    st.session_state.messages = save_game.messages
    st.session_state.current_save_id = save_game.save_id
    st.session_state.current_character_id = save_game.character_id or None
    st.session_state.action_suggestions = get_action_suggestions(save_game)
    st.session_state.game_started = True
    st.session_state.page = "game"
    return True
