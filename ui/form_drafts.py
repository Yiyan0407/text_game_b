"""在页面切换、rerun 与浏览器刷新之间保留未提交的表单草稿。"""

from __future__ import annotations

import streamlit as st

from game.character_creation import AbilityRollDetail, RolledAbilities
from game.draft_store import DraftStore


def seed_widget(key: str, value) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def draft_store() -> DraftStore:
    profile_id = st.session_state.get("current_profile_id") or "_guest"
    return DraftStore(profile_id)


def character_draft_prefix(scenario_id: str) -> str:
    return f"char_create_{scenario_id}"


def character_draft_keys(scenario_id: str) -> tuple[str, str, str]:
    prefix = character_draft_prefix(scenario_id)
    return f"{prefix}_name", f"{prefix}_background", f"{prefix}_world"


def _character_draft_slug(scenario_id: str) -> str:
    return f"character_{scenario_id}"


def _scenario_editor_slug(scenario_id: str, creating: bool) -> str:
    return f"scenario_{scenario_id}_{int(creating)}"


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


def rolled_abilities_to_dict(rolled: RolledAbilities) -> dict:
    return {
        "details": [
            {
                "key": detail.key,
                "field": detail.field,
                "label": detail.label,
                "score": detail.score,
                "rolls": list(detail.rolls),
                "dropped": detail.dropped,
            }
            for detail in rolled.details
        ]
    }


def rolled_abilities_from_dict(payload: dict | None) -> RolledAbilities | None:
    if not payload or not isinstance(payload.get("details"), list):
        return None
    details: list[AbilityRollDetail] = []
    for item in payload["details"]:
        if not isinstance(item, dict):
            continue
        details.append(
            AbilityRollDetail(
                key=str(item.get("key", "")),
                field=str(item.get("field", "")),
                label=str(item.get("label", "")),
                score=int(item.get("score", 0)),
                rolls=tuple(int(v) for v in item.get("rolls", [])),
                dropped=int(item.get("dropped", 0)),
            )
        )
    if len(details) != 6:
        return None
    return RolledAbilities(details=tuple(details))


def _character_fields_empty(fields: dict, *, default_world: str) -> bool:
    if str(fields.get("name", "")).strip() or str(fields.get("background", "")).strip():
        return False
    return str(fields.get("world_id", default_world)) == default_world


def init_character_draft(scenario_id: str, default_world: str) -> None:
    name_key, background_key, world_key = character_draft_keys(scenario_id)
    disk = draft_store().load(_character_draft_slug(scenario_id)) or {}
    fields = disk.get("fields") if isinstance(disk.get("fields"), dict) else {}

    seed_widget(name_key, fields.get("name", ""))
    seed_widget(background_key, fields.get("background", ""))
    seed_widget(world_key, fields.get("world_id") or default_world)


def restore_character_draft_extras(scenario_id: str) -> None:
    disk = draft_store().load(_character_draft_slug(scenario_id)) or {}
    rolled = rolled_abilities_from_dict(disk.get("rolled_abilities"))
    if rolled is not None and "rolled_abilities" not in st.session_state:
        st.session_state.rolled_abilities = rolled


def sync_character_draft_to_disk(scenario_id: str, *, default_world: str) -> None:
    name_key, background_key, world_key = character_draft_keys(scenario_id)
    fields = {
        "name": st.session_state.get(name_key, ""),
        "background": st.session_state.get(background_key, ""),
        "world_id": st.session_state.get(world_key, default_world),
    }
    store = draft_store()
    slug = _character_draft_slug(scenario_id)
    if _character_fields_empty(fields, default_world=default_world):
        store.delete(slug)
        return

    payload: dict = {
        "kind": "character_create",
        "scenario_id": scenario_id,
        "fields": fields,
    }
    rolled = st.session_state.get("rolled_abilities")
    if isinstance(rolled, RolledAbilities):
        payload["rolled_abilities"] = rolled_abilities_to_dict(rolled)
    store.save(slug, payload)


def clear_character_draft(scenario_id: str) -> None:
    for key in character_draft_keys(scenario_id):
        st.session_state.pop(key, None)
    draft_store().delete(_character_draft_slug(scenario_id))


def scenario_editor_field_key(scenario_id: str, creating: bool, field: str) -> str:
    return f"scenario_edit_{field}_{scenario_id}_{int(creating)}"


def scenario_editor_widget_keys(scenario_id: str, creating: bool) -> list[str]:
    fields = (
        "title",
        "description",
        "world_id",
        "world",
        "tone",
        "opening_scene_id",
        "opening_scene_name",
        "opening_prompt",
        "custom_world_overlay",
    )
    return [
        scenario_editor_field_key(scenario_id, creating, field) for field in fields
    ]


def scenario_editor_table_keys(scenario_id: str, creating: bool) -> tuple[str, str, str]:
    return (
        f"scenario_edit_quests_{scenario_id}_{creating}",
        f"scenario_edit_nodes_{scenario_id}_{creating}",
        f"scenario_edit_endings_{scenario_id}_{creating}",
    )


def init_scenario_editor_draft(scenario, *, creating: bool) -> None:
    disk = draft_store().load(_scenario_editor_slug(scenario.id, creating)) or {}
    disk_fields = disk.get("fields") if isinstance(disk.get("fields"), dict) else {}

    seeds = {
        "title": scenario.title,
        "description": scenario.description,
        "world_id": scenario.world_id,
        "world": scenario.world,
        "tone": scenario.tone,
        "opening_scene_id": scenario.opening_scene_id,
        "opening_scene_name": scenario.opening_scene_name,
        "opening_prompt": scenario.opening_prompt,
        "custom_world_overlay": scenario.custom_world_overlay,
    }
    for field, default in seeds.items():
        seed_widget(
            scenario_editor_field_key(scenario.id, creating, field),
            disk_fields.get(field, default),
        )

    quests_key, nodes_key, endings_key = scenario_editor_table_keys(scenario.id, creating)
    if quests_key not in st.session_state and isinstance(disk.get("quests"), list):
        st.session_state[quests_key] = disk["quests"]
    if nodes_key not in st.session_state and isinstance(disk.get("nodes"), list):
        st.session_state[nodes_key] = disk["nodes"]
    if endings_key not in st.session_state and isinstance(disk.get("endings"), list):
        st.session_state[endings_key] = disk["endings"]


def sync_scenario_editor_draft_to_disk(scenario_id: str, *, creating: bool) -> None:
    fields = {
        field: st.session_state.get(
            scenario_editor_field_key(scenario_id, creating, field), ""
        )
        for field in (
            "title",
            "description",
            "world_id",
            "world",
            "tone",
            "opening_scene_id",
            "opening_scene_name",
            "opening_prompt",
            "custom_world_overlay",
        )
    }
    quests_key, nodes_key, endings_key = scenario_editor_table_keys(scenario_id, creating)
    quests = _coerce_editor_rows(st.session_state.get(quests_key))
    nodes = _coerce_editor_rows(st.session_state.get(nodes_key))
    endings = _coerce_editor_rows(st.session_state.get(endings_key))

    store = draft_store()
    slug = _scenario_editor_slug(scenario_id, creating)
    if not str(fields.get("title", "")).strip() and not str(fields.get("description", "")).strip():
        if not quests and not nodes and not endings:
            store.delete(slug)
            return

    store.save(
        slug,
        {
            "kind": "scenario_editor",
            "scenario_id": scenario_id,
            "creating": creating,
            "fields": fields,
            "quests": quests,
            "nodes": nodes,
            "endings": endings,
        },
    )


def clear_scenario_editor_draft(scenario_id: str, *, creating: bool) -> None:
    for key in scenario_editor_widget_keys(scenario_id, creating):
        st.session_state.pop(key, None)
    for key in scenario_editor_table_keys(scenario_id, creating):
        st.session_state.pop(key, None)
    draft_store().delete(_scenario_editor_slug(scenario_id, creating))


def init_scenario_generator_draft() -> None:
    disk = draft_store().load("scenario_generator_custom") or {}
    fields = disk.get("fields") if isinstance(disk.get("fields"), dict) else {}
    seed_widget("gen_custom_desc", fields.get("description", ""))
    seed_widget("gen_custom_world", fields.get("world_id", "自动"))


def sync_scenario_generator_draft_to_disk() -> None:
    description = st.session_state.get("gen_custom_desc", "")
    world_id = st.session_state.get("gen_custom_world", "自动")
    store = draft_store()
    if not str(description).strip():
        store.delete("scenario_generator_custom")
        return
    store.save(
        "scenario_generator_custom",
        {
            "kind": "scenario_generator_custom",
            "fields": {
                "description": description,
                "world_id": world_id,
            },
        },
    )


def init_new_profile_draft() -> None:
    disk = DraftStore("_guest").load("new_profile") or {}
    fields = disk.get("fields") if isinstance(disk.get("fields"), dict) else {}
    seed_widget("new_profile_name", fields.get("name", ""))


def sync_new_profile_draft_to_disk() -> None:
    name = st.session_state.get("new_profile_name", "")
    store = DraftStore("_guest")
    if not str(name).strip():
        store.delete("new_profile")
        return
    store.save(
        "new_profile",
        {
            "kind": "new_profile",
            "fields": {"name": name},
        },
    )


def clear_new_profile_draft() -> None:
    st.session_state.pop("new_profile_name", None)
    DraftStore("_guest").delete("new_profile")
