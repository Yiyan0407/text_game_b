import streamlit as st

from chain.scenario_generator import ScenarioGenerationError, ScenarioGenerator
from config.settings import get_settings
from config.worlds import GENERATION_MODES, THEME_HINTS, WORLD_OPTIONS
from game.scenario import Scenario
from game.scenario_loader import can_delete_scenario, delete_generated_scenario, load_scenario, save_scenario
from ui.form_drafts import init_scenario_generator_draft, sync_scenario_generator_draft_to_disk
from ui.loading import run_with_spinner
from ui.scenario_editor import render_scenario_editor


def clear_scenario_from_session(scenario_id: str) -> None:
    generated = st.session_state.get("generated_scenario")
    if generated is not None and generated.id == scenario_id:
        st.session_state.pop("generated_scenario", None)
    selected = st.session_state.get("selected_scenario")
    if selected is not None and selected.id == scenario_id:
        st.session_state.pop("selected_scenario", None)


def render_scenario_generator() -> None:
    st.title("✨ 剧本工坊")
    st.markdown("AI 随机/描述生成，或手动从零撰写完整剧本。")

    settings = get_settings()

    tab_theme, tab_custom, tab_manual = st.tabs(
        ["🎲 主题随机", "✍️ AI 自定义", "📝 手动撰写"]
    )

    with tab_theme:
        if not settings.openai_api_key:
            st.warning("请先在 `.env` 中配置 `OPENAI_API_KEY`。")
        _render_theme_generator(settings)

    with tab_custom:
        if not settings.openai_api_key:
            st.warning("请先在 `.env` 中配置 `OPENAI_API_KEY`。")
        _render_custom_generator(settings)

    with tab_manual:
        _render_manual_creator()

    if st.button("返回主菜单"):
        st.session_state.page = "menu"
        st.rerun()


def _render_mode_selector(key: str) -> str:
    mode_labels = list(GENERATION_MODES.keys())
    return st.radio(
        "生成内容",
        options=mode_labels,
        format_func=lambda k: GENERATION_MODES[k],
        horizontal=True,
        key=f"gen_mode_{key}",
    )


def _render_theme_generator(settings) -> None:
    world_id = st.selectbox(
        "世界观",
        options=list(WORLD_OPTIONS.keys()),
        format_func=lambda k: WORLD_OPTIONS[k],
        key="gen_theme_world",
    )
    hints = THEME_HINTS.get(world_id, ["完全随机"])
    theme = st.selectbox("主题方向", options=hints, key="gen_theme_hint")
    mode = _render_mode_selector("theme")

    if st.button("🎲 随机生成", type="primary", use_container_width=True):
        if not settings.openai_api_key:
            st.error("缺少 OPENAI_API_KEY。")
            return
        _run_generation(
            lambda gen: gen.generate_from_theme(world_id, theme, mode=mode),
        )


def _render_custom_generator(settings) -> None:
    init_scenario_generator_draft()
    description = st.text_area(
        "描述你想要的设定或故事",
        placeholder=(
            "例如：近未来上海，记忆可以被买卖；"
            "或：修仙界有个只会炼毒丹的废柴弟子，意外发现毒丹能破咒……"
        ),
        height=140,
        key="gen_custom_desc",
    )
    world_id = st.selectbox(
        "世界观（可选，留空则 AI 自行判断）",
        options=["自动"] + list(WORLD_OPTIONS.keys()),
        format_func=lambda k: "AI 自动选择" if k == "自动" else WORLD_OPTIONS[k],
        key="gen_custom_world",
    )
    mode = _render_mode_selector("custom")
    sync_scenario_generator_draft_to_disk()

    if st.button("✨ 根据描述生成", type="primary", use_container_width=True):
        if not description.strip():
            st.error("请先输入描述。")
            return
        if not settings.openai_api_key:
            st.error("缺少 OPENAI_API_KEY。")
            return
        chosen_world = None if world_id == "自动" else world_id
        _run_generation(
            lambda gen: gen.generate_from_description(
                description.strip(),
                world_id=chosen_world,
                mode=mode,
            ),
        )


def _render_manual_creator() -> None:
    from game.scenario_loader import blank_scenario_template

    st.caption("无需 API Key，填写后保存即可在新游戏中使用。")
    world_id = st.selectbox(
        "默认世界观",
        options=list(WORLD_OPTIONS.keys()),
        format_func=lambda k: WORLD_OPTIONS[k],
        key="manual_scenario_world",
    )
    draft = blank_scenario_template(world_id)
    draft.world_id = world_id
    created = render_scenario_editor(draft, creating=True)
    if created is not None:
        st.session_state.generated_scenario = created
        st.session_state.scenario_preview_view = "预览"
        st.session_state.page = "preview_scenario"
        st.rerun()


def _run_generation(generate_fn) -> None:
    generator = ScenarioGenerator()
    try:
        scenario = run_with_spinner("AI 正在撰写剧本……", lambda: generate_fn(generator))
    except ScenarioGenerationError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"生成失败：{exc}")
        return

    with st.spinner("保存剧本中……"):
        save_scenario(scenario, generated=True)
    st.session_state.generated_scenario = scenario
    st.session_state.page = "preview_scenario"
    st.rerun()


def render_scenario_preview() -> None:
    scenario: Scenario | None = st.session_state.get("generated_scenario")
    if not scenario:
        st.session_state.page = "generate_scenario"
        st.rerun()
        return

    st.title("📜 剧本预览")
    view = st.radio(
        "视图",
        options=["预览", "编辑"],
        horizontal=True,
        key="scenario_preview_view",
    )

    if view == "编辑":
        updated = render_scenario_editor(scenario)
        if updated is not None:
            st.session_state.generated_scenario = updated
            st.session_state.selected_scenario = updated
            st.rerun()
        st.divider()
        _render_preview_actions(scenario)
        return

    _render_scenario_preview_content(scenario)
    _render_preview_actions(scenario)


def _render_scenario_preview_content(scenario: Scenario) -> None:
    world_label = WORLD_OPTIONS.get(scenario.world_id, scenario.world_id)
    st.markdown(f"**{scenario.title}** · 🌍 {world_label}")
    st.caption(scenario.description)

    with st.expander("世界观与基调", expanded=True):
        st.markdown(f"**世界：** {scenario.world}")
        st.markdown(f"**基调：** {scenario.tone}")
        if scenario.custom_world_overlay:
            st.markdown(scenario.custom_world_overlay)
        st.markdown(f"**开场：** {scenario.opening_prompt}")

    if scenario.initial_quests:
        st.markdown("**初始任务**")
        for quest in scenario.initial_quests:
            st.markdown(f"- {quest.title}：{quest.description}")

    if scenario.key_nodes:
        st.markdown("**关键节点**")
        for node in scenario.key_nodes:
            st.markdown(f"- {node.title}：{node.description}")

    if scenario.endings:
        st.markdown("**可能结局**")
        for ending in scenario.endings:
            st.markdown(f"- {ending.title}：{ending.condition}")


def _render_preview_actions(scenario: Scenario) -> None:
    col1, col2, col3 = st.columns(3)
    if col1.button("🎮 开始创建角色", type="primary", use_container_width=True):
        st.session_state.selected_scenario = scenario
        st.session_state.page = "select_character"
        st.rerun()
    if col2.button("🔄 重新生成", use_container_width=True):
        st.session_state.page = "generate_scenario"
        st.rerun()
    if col3.button("返回主菜单", use_container_width=True):
        st.session_state.page = "menu"
        st.rerun()

    if scenario.is_generated and can_delete_scenario(scenario.id):
        if st.button("🗑️ 删除此剧本", use_container_width=True):
            if delete_generated_scenario(scenario.id):
                clear_scenario_from_session(scenario.id)
                st.session_state.page = "select_scenario"
                st.toast(f"已删除剧本：{scenario.title}")
                st.rerun()
            else:
                st.error("删除失败，剧本可能已被移除。")


def open_scenario_for_edit(scenario_id: str) -> None:
    scenario = load_scenario(scenario_id)
    st.session_state.generated_scenario = scenario
    st.session_state.scenario_preview_view = "编辑"
    st.session_state.page = "preview_scenario"
