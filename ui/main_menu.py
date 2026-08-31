from collections import Counter

from datetime import datetime, timezone

import streamlit as st

from config.worlds import DEFAULT_WORLD_ID, WORLD_OPTIONS
from game.profile import CharacterCard
from game.save import SaveManager
from game.scenario import Scenario
from game.scenario_loader import delete_generated_scenario, list_scenarios
from ui.form_drafts import (
    character_draft_keys,
    clear_character_draft,
    get_rolled_abilities,
    init_character_draft,
    restore_character_draft_extras,
    rolled_abilities_prev_total_key,
    rolled_abilities_session_key,
    sync_character_draft_to_disk,
)
from ui.risky_action import (
    ACTION_DELETE_SAVE,
    ACTION_DELETE_SCENARIO,
    PENDING,
    handle_risky_action_prompt,
    queue_delete_save,
    queue_delete_scenario,
)
from ui.scenario_generator import clear_scenario_from_session
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


def _handle_pending_risky_deletes(save_manager: SaveManager) -> None:
    result = handle_risky_action_prompt()
    if result is PENDING or not result:
        return

    action = result["action"]
    ctx = result["context"]
    if action == ACTION_DELETE_SAVE:
        save_manager.delete(ctx["save_id"])
        st.toast(f"已删除存档：{ctx['label']}")
    elif action == ACTION_DELETE_SCENARIO:
        if delete_generated_scenario(ctx["scenario_id"]):
            clear_scenario_from_session(ctx["scenario_id"])
            st.toast(f"已删除剧本：{ctx['title']}")
        else:
            st.error("删除失败，剧本可能已被移除。")
    st.rerun()


def render_main_menu(save_manager: SaveManager) -> None:
    _handle_pending_risky_deletes(save_manager)
    st.title("🎲 AI 跑团")
    render_profile_switcher(st.session_state.profile_manager)
    st.markdown("选择继续冒险，或开始新的模组。")

    saves = save_manager.list_saves()
    col1, col2, col3 = st.columns(3)
    if col1.button("🆕 新游戏", use_container_width=True, type="primary"):
        st.session_state.page = "select_scenario"
        st.rerun()

    if col2.button("✨ 剧本工坊", use_container_width=True):
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
                queue_delete_save(
                    meta.save_id,
                    label=f"{meta.character_name} · {meta.scenario_title}",
                )
            st.caption(f"📍 {meta.current_scene} · {_format_saved_at(meta.saved_at)}")


def render_load_save(save_manager: SaveManager) -> None:
    _handle_pending_risky_deletes(save_manager)
    st.title("📂 继续冒险")
    saves = save_manager.list_saves()

    if not saves:
        st.info("暂无存档。")
        if st.button("返回主菜单"):
            st.session_state.page = "menu"
            st.rerun()
        return

    duplicate_keys = {
        key
        for key, count in Counter(
            (meta.character_name, meta.scenario_id) for meta in saves
        ).items()
        if count > 1
    }
    if duplicate_keys:
        st.info(
            "同一角色在同一模组可能有多条存档（例如多次开新局）。"
            "请根据**回合数**与**保存时间**选择要继续的那一条。"
        )

    for meta in saves:
        with st.container(border=True):
            st.markdown(f"**{meta.character_name}** — {meta.scenario_title}")
            st.caption(
                f"回合 {meta.turn_count} · 📍 {meta.current_scene} · "
                f"{_format_saved_at(meta.saved_at)}"
            )
            if (meta.character_name, meta.scenario_id) in duplicate_keys:
                st.caption("⚠️ 该角色在本模组另有其他存档，请确认是否读错进度。")
            c1, c2 = st.columns(2)
            if c1.button("读取", key=f"load_{meta.save_id}", use_container_width=True):
                ok = run_with_spinner(
                    "读取存档中……",
                    lambda save_id=meta.save_id: load_save_into_session(save_manager, meta.save_id),
                )
                if ok:
                    st.rerun()
            if c2.button("删除", key=f"del_{meta.save_id}", use_container_width=True):
                queue_delete_save(
                    meta.save_id,
                    label=f"{meta.character_name} · {meta.scenario_title}",
                )

    if st.button("返回主菜单"):
        st.session_state.page = "menu"
        st.rerun()


def render_scenario_selection() -> None:
    save_manager: SaveManager = st.session_state.save_manager
    _handle_pending_risky_deletes(save_manager)
    st.title("🆕 选择模组")
    st.caption("模组简介描述的是事件与场景，不是你的固定身份；选角后开局会自动衔接你的角色背景。")
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
            if scenario.is_generated:
                c1, c2, c3 = st.columns(3)
                if c1.button("选择", key=f"scenario_{scenario.id}", use_container_width=True):
                    st.session_state.selected_scenario = scenario
                    preselected = st.session_state.get("selected_character_card")
                    if preselected:
                        start_new_game_with_card(scenario, preselected)
                    else:
                        st.session_state.page = "select_character"
                    st.rerun()
                if c2.button("✏️ 编辑", key=f"edit_scenario_{scenario.id}", use_container_width=True):
                    from ui.scenario_generator import open_scenario_for_edit

                    open_scenario_for_edit(scenario.id)
                    st.rerun()
                if c3.button("🗑️ 删除", key=f"del_scenario_{scenario.id}", use_container_width=True):
                    queue_delete_scenario(scenario.id, title=scenario.title)
            elif st.button("选择", key=f"scenario_{scenario.id}", use_container_width=True):
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


def render_character_creation(
    scenario: Scenario,
    *,
    creating_new_card: bool = False,
    game_config=None,
) -> None:
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
    init_character_draft(scenario.id, default_world)
    restore_character_draft_extras(scenario.id)
    name_key, background_key, world_key = character_draft_keys(scenario.id)

    rolled = get_rolled_abilities(scenario.id, default_factory=roll_ability_scores)
    prev_total_key = rolled_abilities_prev_total_key(scenario.id)

    st.subheader("属性掷骰")
    st.caption("每项属性均为 4d6 去掉最低一颗（经典创角规则），点数不可手动调整。")

    total = rolled.total_score()
    prev_total = st.session_state.get(prev_total_key)
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
        st.session_state[prev_total_key] = rolled.total_score()
        st.session_state[rolled_abilities_session_key(scenario.id)] = roll_ability_scores()
        sync_character_draft_to_disk(scenario.id, default_world=default_world)
        st.rerun()

    selected_world = st.selectbox(
        "规则/世界观包",
        options=list(WORLD_OPTIONS.keys()),
        format_func=lambda k: WORLD_OPTIONS[k],
        key=world_key,
    )
    name = st.text_input("角色姓名", placeholder="例如：艾拉", key=name_key)
    background = st.text_area(
        "角色背景",
        placeholder="例如：前海军斥候，为还债来到灰港做佣兵。",
        height=100,
        key=background_key,
    )
    st.caption(
        "背景应描述身份与动机。"
        "若启用审核，请勿写开局无敌、满级、神器或巨额资源。"
        "职业不必与模组默认开场一致，开局会自动衔接你的身份。"
        "背景审核通过后会由 AI 生成 1–3 项初始技能。"
        "草稿会自动保存到本机，切换页面或刷新浏览器后可继续编辑。"
    )

    if game_config is None:
        from ui.game_options import render_game_options

        game_config = render_game_options(show_background_validation=True)

    sync_character_draft_to_disk(scenario.id, default_world=default_world)
    start_clicked = st.button("开始冒险", type="primary", use_container_width=True)

    if start_clicked:
        if not name.strip():
            st.error("请填写角色姓名。")
            return
        if not settings.openai_api_key:
            st.error("缺少 OPENAI_API_KEY，无法启动游戏。")
            return

        final_background = background.strip() or "一位初到灰港的冒险者。"
        from chain.background_validator import BackgroundValidator
        from chain.starter_skills_generator import (
            StarterSkillsGenerationError,
            StarterSkillsGenerator,
        )

        with st.spinner("正在审核角色背景……"):
            if game_config.enable_background_validation:
                bg_result = BackgroundValidator().evaluate(
                    final_background,
                    world_id=selected_world,
                    scenario=scenario,
                )
            else:
                from game.background_validator import BackgroundValidationResult

                bg_result = BackgroundValidationResult(approved=True)
        if not bg_result.approved:
            st.error(f"背景无法通过审核：{bg_result.rejection_reason}")
            return

        try:
            with st.spinner("正在根据背景生成初始技能……"):
                starter_skills = StarterSkillsGenerator().generate(
                    final_background,
                    world_id=selected_world,
                )
        except StarterSkillsGenerationError as exc:
            st.error(str(exc))
            return

        character = build_character(
            name=name.strip(),
            background=final_background,
            rolled=rolled,
            starter_skills=starter_skills,
        )
        active_scenario = scenario.model_copy(update={"world_id": selected_world})
        clear_character_draft(scenario.id)

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
        start_new_game(active_scenario, character, character_card=saved_card, game_config=game_config)

    if st.button("返回", key="back_from_character"):
        if st.session_state.get("generated_scenario"):
            st.session_state.page = "preview_scenario"
        elif creating_new_card:
            st.session_state.page = "select_character"
        else:
            st.session_state.page = "select_scenario"
        st.rerun()


def start_new_game_with_card(
    scenario: Scenario,
    card: CharacterCard,
    *,
    game_config=None,
) -> None:
    from game.game_config import GameConfig, default_game_config

    world_id = card.preferred_world_id or scenario.world_id
    active_scenario = scenario.model_copy(update={"world_id": world_id})
    character = card.to_runtime_character()
    st.session_state.pop("selected_character_card", None)
    config = game_config or default_game_config()
    start_new_game(active_scenario, character, character_card=card, game_config=config)


def start_new_game(
    scenario: Scenario,
    character,
    *,
    character_card: CharacterCard | None = None,
    career_context: str = "",
    game_config=None,
) -> None:
    from config.settings import get_settings
    from game.game_config import GameConfig, default_game_config
    from game.models import ChatMessage, GameState
    from game.save import SaveGame
    from game.profile import prepare_card_for_new_campaign
    from game.session import append_tool_events, persist_save

    config: GameConfig = game_config or default_game_config()

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
        game_config=config,
    )

    st.session_state.character = character
    st.session_state.game_state = game_state
    st.session_state.scenario = scenario
    st.session_state.game_config = config
    st.session_state.current_save_id = save_game.save_id
    st.session_state.current_character_id = character_card.card_id if character_card else None
    st.session_state.messages = []
    st.session_state.action_suggestions = []
    st.session_state.game_started = True
    st.session_state.page = "game"

    if settings.enable_streaming:
        progress = LoadingPlaceholder()
        progress.show("编织入场逻辑……")
        opening_completed = False
        rollback_turn = None
        try:
            (
                rejection,
                pre_tool_events,
                run_state_phase,
                text_stream,
                run_item_sync_phase,
                run_finalize_phase,
                finish_turn,
                turn_context,
                rollback_turn,
            ) = orchestrator.start_game_stream(
                character, game_state, scenario, career_context=career_context, game_config=config
            )
            from game.session import append_tool_events
            from ui.streaming import finalize_streaming_turn, render_phased_turn

            append_tool_events(pre_tool_events)

            state_events, full = render_phased_turn(
                pre_tool_events,
                run_state_phase,
                text_stream,
                loading=progress,
            )
            append_tool_events(state_events)
            turn = finalize_streaming_turn(
                full,
                run_item_sync_phase=run_item_sync_phase,
                run_finalize_phase=run_finalize_phase,
                finish_turn=finish_turn,
            )
            item_events = [
                event
                for event in turn.tool_events
                if event not in pre_tool_events and event not in state_events
            ]
            append_tool_events(item_events)
            progress.clear()
            st.session_state.messages.append(
                ChatMessage(role="assistant", content=full or turn.response)
            )
            if turn.action_suggestions:
                st.session_state.action_suggestions = turn.action_suggestions
            opening_completed = True
        except Exception as exc:
            if rollback_turn:
                rollback_turn()
            st.session_state.messages = []
            st.session_state.game_started = False
            st.session_state.page = "menu"
            st.error(f"开场生成失败：{exc}")
            return
        if not opening_completed:
            return
    else:
        with st.spinner("正在生成入场逻辑并编织开场……"):
            turn = orchestrator.start_game(
                character, game_state, scenario, career_context=career_context, game_config=config
            )
        from game.session import append_turn_result

        append_turn_result(turn)
        st.session_state.action_suggestions = turn.action_suggestions

    persist_save()
    st.rerun()


def load_save_into_session(save_manager: SaveManager, save_id: str) -> bool:
    from game.scenario_loader import ScenarioNotFoundError, load_scenario
    from game.session import apply_save_to_session

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

    apply_save_to_session(save_game, scenario)
    st.session_state.page = "game"
    return True
