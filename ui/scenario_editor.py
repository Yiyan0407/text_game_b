from __future__ import annotations

import streamlit as st
from pydantic import ValidationError

from config.worlds import WORLD_OPTIONS
from game.models import Quest
from game.scenario import Scenario, ScenarioEnding, ScenarioNode
from game.scenario_loader import save_scenario, slugify_entity_id
from ui.form_drafts import (
    clear_scenario_editor_draft,
    init_scenario_editor_draft,
    scenario_editor_field_key,
)


def _clean_row(row: dict) -> dict:
    return {key: "" if value is None else str(value).strip() for key, value in row.items()}


def _resolve_opening_scene_id(
    opening_scene_name: str,
    *,
    previous_id: str,
    previous_name: str,
) -> str:
    name = opening_scene_name.strip() or "起点"
    if previous_id.strip() and name == previous_name.strip():
        return previous_id.strip()
    return slugify_entity_id(name, prefix="start")


def _rows_to_quests(rows: list[dict], existing: list[Quest]) -> list[Quest]:
    by_title = {q.title.strip(): q.id for q in existing if q.title.strip()}
    used = {q.id for q in existing if q.id}
    quests: list[Quest] = []
    for row in rows:
        cleaned = _clean_row(row)
        title = cleaned.get("title") or ""
        if not title:
            continue
        quest_id = by_title.get(title.strip()) or slugify_entity_id(
            title, prefix="quest", existing=used
        )
        used.add(quest_id)
        quests.append(
            Quest.model_validate(
                {
                    "id": quest_id,
                    "title": title,
                    "status": cleaned.get("status") or "active",
                    "description": cleaned.get("description", ""),
                }
            )
        )
    return quests


def _rows_to_nodes(rows: list[dict], existing: list[ScenarioNode]) -> list[ScenarioNode]:
    by_title = {n.title.strip(): n.id for n in existing if n.title.strip()}
    used = {n.id for n in existing if n.id}
    nodes: list[ScenarioNode] = []
    for row in rows:
        cleaned = _clean_row(row)
        title = cleaned.get("title") or ""
        if not title:
            continue
        node_id = by_title.get(title.strip()) or slugify_entity_id(
            title, prefix="node", existing=used
        )
        used.add(node_id)
        nodes.append(
            ScenarioNode.model_validate(
                {
                    "id": node_id,
                    "title": title,
                    "description": cleaned.get("description", ""),
                    "beats": [
                        part.strip()
                        for part in str(cleaned.get("beats", "")).splitlines()
                        if part.strip()
                    ],
                }
            )
        )
    return nodes


def _rows_to_endings(rows: list[dict], existing: list[ScenarioEnding]) -> list[ScenarioEnding]:
    by_title = {e.title.strip(): e.id for e in existing if e.title.strip()}
    used = {e.id for e in existing if e.id}
    endings: list[ScenarioEnding] = []
    for row in rows:
        cleaned = _clean_row(row)
        title = cleaned.get("title") or ""
        if not title:
            continue
        ending_id = by_title.get(title.strip()) or slugify_entity_id(
            title, prefix="ending", existing=used
        )
        used.add(ending_id)
        endings.append(
            ScenarioEnding.model_validate(
                {
                    "id": ending_id,
                    "title": title,
                    "condition": cleaned.get("condition", ""),
                }
            )
        )
    return endings


def _editor_rows(items, *, fields: list[str]) -> list[dict]:
    rows: list[dict] = []
    for item in items:
        if hasattr(item, "model_dump"):
            data = item.model_dump()
        elif isinstance(item, dict):
            data = item
        else:
            continue
        row: dict[str, str] = {}
        for field in fields:
            if field == "beats":
                beats = data.get("beats") or []
                if isinstance(beats, list):
                    row[field] = "\n".join(str(part) for part in beats if str(part).strip())
                else:
                    row[field] = str(beats or "")
            else:
                row[field] = str(data.get(field, "") or "")
        rows.append(row)
    return rows or [{field: "" for field in fields}]


def build_scenario_from_editor(
    scenario: Scenario,
    *,
    title: str,
    description: str,
    world_id: str,
    world: str,
    tone: str,
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

    opening_name = opening_scene_name.strip() or "起点"
    opening_scene_id = _resolve_opening_scene_id(
        opening_name,
        previous_id=scenario.opening_scene_id,
        previous_name=scenario.opening_scene_name,
    )

    return Scenario.model_validate(
        {
            "id": scenario_id,
            "title": resolved_title,
            "description": description.strip(),
            "world_id": world_id,
            "world": world.strip(),
            "tone": tone.strip(),
            "opening_scene_id": opening_scene_id,
            "opening_scene_name": opening_name,
            "opening_prompt": opening_prompt.strip(),
            "custom_world_overlay": custom_world_overlay.strip(),
            "initial_quests": [
                q.model_dump() for q in _rows_to_quests(quest_rows, scenario.initial_quests)
            ],
            "key_nodes": [
                n.model_dump() for n in _rows_to_nodes(node_rows, scenario.key_nodes)
            ],
            "endings": [
                e.model_dump() for e in _rows_to_endings(ending_rows, scenario.endings)
            ],
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
        st.caption(f"剧本 ID：`{scenario.id}`（系统生成，不可修改）")

    submit_label = "💾 创建并保存" if creating else "💾 保存修改"
    init_scenario_editor_draft(scenario, creating=creating)

    title_key = scenario_editor_field_key(scenario.id, creating, "title")
    description_key = scenario_editor_field_key(scenario.id, creating, "description")
    world_id_key = scenario_editor_field_key(scenario.id, creating, "world_id")
    world_key = scenario_editor_field_key(scenario.id, creating, "world")
    tone_key = scenario_editor_field_key(scenario.id, creating, "tone")
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
    opening_scene_name = st.text_input(
        "开场地点名称",
        key=opening_scene_name_key,
        help="玩家看到的第一个地点，如 灰港·海鸥尾酒馆",
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
    st.caption("地点/任务/结局的内部 ID 由系统自动生成；游戏中 scene_id 由 AI 按地点名维护，无需填写。")

    st.markdown("**初始任务**")
    quest_rows = st.data_editor(
        _editor_rows(scenario.initial_quests, fields=["title", "status", "description"]),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "title": st.column_config.TextColumn("标题", required=True),
            "status": st.column_config.SelectboxColumn(
                "状态", options=["active", "completed", "failed"], required=True
            ),
            "description": st.column_config.TextColumn("描述", width="large"),
        },
        key=f"scenario_edit_quests_{scenario.id}_{creating}",
    )

    st.markdown("**关键节点**")
    st.caption("「待完成要素」每行一条，供按剧本/平衡模式追踪进度。")
    node_rows = st.data_editor(
        _editor_rows(scenario.key_nodes, fields=["title", "description", "beats"]),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "title": st.column_config.TextColumn("地点/剧情点", required=True),
            "description": st.column_config.TextColumn("描述", width="large"),
            "beats": st.column_config.TextColumn(
                "待完成要素（每行一条）",
                width="large",
                help="例如：德国特工通讯响起；江一燕在实验室出场",
            ),
        },
        key=f"scenario_edit_nodes_{scenario.id}_{creating}",
    )

    st.markdown("**可能结局**")
    ending_rows = st.data_editor(
        _editor_rows(scenario.endings, fields=["title", "condition"]),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "title": st.column_config.TextColumn("标题", required=True),
            "condition": st.column_config.TextColumn("达成条件", width="large"),
        },
        key=f"scenario_edit_endings_{scenario.id}_{creating}",
    )

    submitted = st.button(submit_label, type="primary", use_container_width=True)

    if not submitted:
        return None

    title = st.session_state[title_key]
    description = st.session_state[description_key]
    world_id = st.session_state[world_id_key]
    world = st.session_state[world_key]
    tone = st.session_state[tone_key]
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
