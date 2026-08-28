from __future__ import annotations

import streamlit as st
from pydantic import ValidationError

from config.worlds import WORLD_OPTIONS
from game.models import Quest
from game.scenario import Scenario, ScenarioEnding, ScenarioNode
from game.scenario_loader import save_scenario
from ui.form_drafts import (
    clear_scenario_editor_draft,
    init_scenario_editor_draft,
    scenario_editor_field_key,
    sync_scenario_editor_draft_to_disk,
)


def _clean_row(row: dict) -> dict:
    return {key: "" if value is None else str(value).strip() for key, value in row.items()}


def _rows_to_quests(rows: list[dict]) -> list[Quest]:
    quests: list[Quest] = []
    for row in rows:
        cleaned = _clean_row(row)
        if not cleaned.get("id") and not cleaned.get("title"):
            continue
        quests.append(
            Quest.model_validate(
                {
                    "id": cleaned.get("id") or "quest",
                    "title": cleaned.get("title") or "未命名任务",
                    "status": cleaned.get("status") or "active",
                    "description": cleaned.get("description", ""),
                }
            )
        )
    return quests


def _rows_to_nodes(rows: list[dict]) -> list[ScenarioNode]:
    nodes: list[ScenarioNode] = []
    for row in rows:
        cleaned = _clean_row(row)
        if not cleaned.get("id") and not cleaned.get("title"):
            continue
        nodes.append(
            ScenarioNode.model_validate(
                {
                    "id": cleaned.get("id") or "node",
                    "title": cleaned.get("title") or "未命名节点",
                    "description": cleaned.get("description", ""),
                }
            )
        )
    return nodes


def _rows_to_endings(rows: list[dict]) -> list[ScenarioEnding]:
    endings: list[ScenarioEnding] = []
    for row in rows:
        cleaned = _clean_row(row)
        if not cleaned.get("id") and not cleaned.get("title"):
            continue
        endings.append(
            ScenarioEnding.model_validate(
                {
                    "id": cleaned.get("id") or "ending",
                    "title": cleaned.get("title") or "未命名结局",
                    "condition": cleaned.get("condition", ""),
                }
            )
        )
    return endings


def build_scenario_from_editor(
    scenario: Scenario,
    *,
    title: str,
    description: str,
    world_id: str,
    world: str,
    tone: str,
    opening_scene_id: str,
    opening_scene_name: str,
    opening_prompt: str,
    custom_world_overlay: str,
    quest_rows: list[dict],
    node_rows: list[dict],
    ending_rows: list[dict],
    creating: bool = False,
) -> Scenario:
    resolved_title = title.strip() or scenario.title or "未命名剧本"
    scenario_id = scenario.id
    if creating or scenario_id == "draft_manual":
        from game.scenario_loader import slugify_scenario_id

        scenario_id = slugify_scenario_id(resolved_title)
    return Scenario.model_validate(
        {
            "id": scenario_id,
            "title": resolved_title,
            "description": description.strip(),
            "world_id": world_id,
            "world": world.strip(),
            "tone": tone.strip(),
            "opening_scene_id": opening_scene_id.strip() or "start",
            "opening_scene_name": opening_scene_name.strip() or "起点",
            "opening_prompt": opening_prompt.strip(),
            "custom_world_overlay": custom_world_overlay.strip(),
            "initial_quests": [q.model_dump() for q in _rows_to_quests(quest_rows)],
            "key_nodes": [n.model_dump() for n in _rows_to_nodes(node_rows)],
            "endings": [e.model_dump() for e in _rows_to_endings(ending_rows)],
            "is_generated": scenario.is_generated,
        }
    )


def _coerce_editor_rows(rows) -> list[dict]:
    if rows is None:
        return []
    if isinstance(rows, list):
        return [dict(row) for row in rows]
    if isinstance(rows, dict):
        return [dict(row) for row in rows.values()]
    if hasattr(rows, "to_dict"):
        return rows.to_dict("records")
    return []


def render_scenario_editor(scenario: Scenario, *, creating: bool = False) -> Scenario | None:
    """渲染剧本编辑/创建表单。保存成功时返回 Scenario。"""
    if creating:
        st.markdown("从零填写剧本内容，保存后会写入 `data/scenarios/generated/`，可在新游戏中选择。")
    else:
        st.markdown("修改不合理的内容后点 **保存修改**，会覆盖 `data/scenarios/generated/` 中的同名文件。")
        st.caption(f"剧本 ID：`{scenario.id}`（不可修改，避免存档引用错乱）")

    submit_label = "💾 创建并保存" if creating else "💾 保存修改"
    init_scenario_editor_draft(scenario, creating=creating)

    with st.expander("ID 怎么填？（玩家看不到，给系统/KP 用）", expanded=creating):
        st.markdown(
            """
- **格式**：小写英文 + 下划线，如 `tavern_seagull`、`main_quest`；不要用空格和中文。
- **开场场景 ID**：开局所在地点代号；玩家进入新地点时 KP 会用 `update_scene` 更新场景，**第一个关键节点**可与它对齐。
- **任务 ID**：KP 更新任务进度时用（`update_quest`）；同一剧本内不要重复。
- **节点 ID**：给 KP 参考的关键地点/剧情点代号；常与场景 ID 一致，如节点 `harbor_dock` ↔ 场景 `harbor_dock`。
- **结局 ID**：结局条目代号，配合「达成条件」描述即可。
- **省事写法**：`start` / `quest1` / `node1` / `ending1` 也能用。
            """
        )

    st.caption("草稿会自动保存到本机；切换页面或刷新浏览器后可继续编辑。")

    title_key = scenario_editor_field_key(scenario.id, creating, "title")
    description_key = scenario_editor_field_key(scenario.id, creating, "description")
    world_id_key = scenario_editor_field_key(scenario.id, creating, "world_id")
    world_key = scenario_editor_field_key(scenario.id, creating, "world")
    tone_key = scenario_editor_field_key(scenario.id, creating, "tone")
    opening_scene_id_key = scenario_editor_field_key(scenario.id, creating, "opening_scene_id")
    opening_scene_name_key = scenario_editor_field_key(scenario.id, creating, "opening_scene_name")
    opening_prompt_key = scenario_editor_field_key(scenario.id, creating, "opening_prompt")
    custom_world_overlay_key = scenario_editor_field_key(
        scenario.id, creating, "custom_world_overlay"
    )

    title = st.text_input("标题", key=title_key)
    description = st.text_area("简介", key=description_key, height=80)
    world_id = st.selectbox(
        "世界观规则包",
        options=list(WORLD_OPTIONS.keys()),
        format_func=lambda k: WORLD_OPTIONS[k],
        key=world_id_key,
    )
    world = st.text_input("世界名称", key=world_key)
    tone = st.text_input("基调", key=tone_key)

    st.markdown("**开场**")
    col1, col2 = st.columns(2)
    opening_scene_id = col1.text_input(
        "开场场景 ID",
        key=opening_scene_id_key,
        help="英文代号，如 tavern_seagull；开局默认场景",
    )
    opening_scene_name = col2.text_input(
        "开场场景名称",
        key=opening_scene_name_key,
        help="玩家看到的地点名，如 灰港·海鸥尾酒馆",
    )
    opening_prompt = st.text_area(
        "开场情境 / 委托钩子",
        key=opening_prompt_key,
        height=120,
    )
    custom_world_overlay = st.text_area(
        "世界观扩展设定",
        key=custom_world_overlay_key,
        height=120,
    )

    st.markdown("**初始任务**")
    quest_rows = st.data_editor(
        [q.model_dump() for q in scenario.initial_quests] or [{"id": "", "title": "", "status": "active", "description": ""}],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id": st.column_config.TextColumn(
                "ID", required=True, help="任务代号，如 missing_fishermen"
            ),
            "title": st.column_config.TextColumn("标题", required=True),
            "status": st.column_config.SelectboxColumn(
                "状态", options=["active", "completed", "failed"], required=True
            ),
            "description": st.column_config.TextColumn("描述", width="large"),
        },
        key=f"scenario_edit_quests_{scenario.id}_{creating}",
    )

    st.markdown("**关键节点**")
    node_rows = st.data_editor(
        [n.model_dump() for n in scenario.key_nodes] or [{"id": "", "title": "", "description": ""}],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id": st.column_config.TextColumn(
                "ID", required=True, help="地点/剧情点代号，如 harbor_dock"
            ),
            "title": st.column_config.TextColumn("标题", required=True),
            "description": st.column_config.TextColumn("描述", width="large"),
        },
        key=f"scenario_edit_nodes_{scenario.id}_{creating}",
    )

    st.markdown("**可能结局**")
    ending_rows = st.data_editor(
        [e.model_dump() for e in scenario.endings] or [{"id": "", "title": "", "condition": ""}],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id": st.column_config.TextColumn(
                "ID", required=True, help="结局代号，如 rescue"
            ),
            "title": st.column_config.TextColumn("标题", required=True),
            "condition": st.column_config.TextColumn("达成条件", width="large"),
        },
        key=f"scenario_edit_endings_{scenario.id}_{creating}",
    )

    submitted = st.button(submit_label, type="primary", use_container_width=True)
    sync_scenario_editor_draft_to_disk(scenario.id, creating=creating)

    if not submitted:
        return None

    title = st.session_state[title_key]
    description = st.session_state[description_key]
    world_id = st.session_state[world_id_key]
    world = st.session_state[world_key]
    tone = st.session_state[tone_key]
    opening_scene_id = st.session_state[opening_scene_id_key]
    opening_scene_name = st.session_state[opening_scene_name_key]
    opening_prompt = st.session_state[opening_prompt_key]
    custom_world_overlay = st.session_state[custom_world_overlay_key]

    if creating and not str(title).strip():
        st.error("请填写剧本标题。")
        return None

    try:
        updated = build_scenario_from_editor(
            scenario,
            title=title,
            description=description,
            world_id=world_id,
            world=world,
            tone=tone,
            opening_scene_id=opening_scene_id,
            opening_scene_name=opening_scene_name,
            opening_prompt=opening_prompt,
            custom_world_overlay=custom_world_overlay,
            quest_rows=_coerce_editor_rows(quest_rows),
            node_rows=_coerce_editor_rows(node_rows),
            ending_rows=_coerce_editor_rows(ending_rows),
            creating=creating,
        )
    except ValidationError as exc:
        st.error(f"保存失败：{exc}")
        return None

    save_scenario(updated, generated=True)
    clear_scenario_editor_draft(scenario.id, creating=creating)
    st.success(f"已保存：{updated.title}")
    return updated
