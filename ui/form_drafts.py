"""在页面切换、rerun 与浏览器刷新之间保留未提交的表单草稿。"""

from __future__ import annotations

import streamlit as st

from game.appearance import AGE_OPTIONS, DEFAULT_AGE, DEFAULT_GENDER, GENDER_OPTIONS
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


def character_draft_keys(scenario_id: str) -> tuple[str, str, str, str, str]:
    prefix = character_draft_prefix(scenario_id)
    return (
        f"{prefix}_name",
        f"{prefix}_background",
        f"{prefix}_world",
        f"{prefix}_gender",
        f"{prefix}_age",
    )


def _character_draft_slug(scenario_id: str) -> str:
    return f"character_{scenario_id}"


def _scenario_editor_slug(scenario_id: str, creating: bool) -> str:
    return f"scenario_{scenario_id}_{int(creating)}"


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


def rolled_abilities_session_key(scenario_id: str) -> str:
    return f"rolled_abilities_{scenario_id}"


def rolled_abilities_prev_total_key(scenario_id: str) -> str:
    return f"rolled_abilities_prev_total_{scenario_id}"


def get_rolled_abilities(scenario_id: str, *, default_factory):
    key = rolled_abilities_session_key(scenario_id)
    if key not in st.session_state:
        st.session_state[key] = default_factory()
    return st.session_state[key]


def clear_rolled_abilities(scenario_id: str) -> None:
    st.session_state.pop(rolled_abilities_session_key(scenario_id), None)
    st.session_state.pop(rolled_abilities_prev_total_key(scenario_id), None)


def _character_draft_has_content(
    fields: dict,
    *,
    default_world: str,
    rolled: RolledAbilities | None,
) -> bool:
    if str(fields.get("name", "")).strip() or str(fields.get("background", "")).strip():
        return True
    if str(fields.get("world_id", default_world)) != default_world:
        return True
    if str(fields.get("gender", DEFAULT_GENDER)) != DEFAULT_GENDER:
        return True
    if str(fields.get("age", DEFAULT_AGE)) != DEFAULT_AGE:
        return True
    return rolled is not None


def init_character_draft(scenario_id: str, default_world: str) -> None:
    name_key, background_key, world_key, gender_key, age_key = character_draft_keys(
        scenario_id
    )
    disk = draft_store().load(_character_draft_slug(scenario_id)) or {}
    fields = disk.get("fields") if isinstance(disk.get("fields"), dict) else {}

    seed_widget(name_key, fields.get("name", ""))
    seed_widget(background_key, fields.get("background", ""))
    seed_widget(world_key, fields.get("world_id") or default_world)
    seed_widget(gender_key, fields.get("gender") or DEFAULT_GENDER)
    seed_widget(age_key, fields.get("age") or DEFAULT_AGE)


def restore_character_draft_extras(scenario_id: str) -> None:
    disk = draft_store().load(_character_draft_slug(scenario_id)) or {}
    rolled = rolled_abilities_from_dict(disk.get("rolled_abilities"))
    rolled_key = rolled_abilities_session_key(scenario_id)
    if rolled is not None and rolled_key not in st.session_state:
        st.session_state[rolled_key] = rolled


def sync_character_draft_to_disk(scenario_id: str, *, default_world: str) -> None:
    name_key, background_key, world_key, gender_key, age_key = character_draft_keys(
        scenario_id
    )
    fields = {
        "name": st.session_state.get(name_key, ""),
        "background": st.session_state.get(background_key, ""),
        "world_id": st.session_state.get(world_key, default_world),
        "gender": st.session_state.get(gender_key, DEFAULT_GENDER),
        "age": st.session_state.get(age_key, DEFAULT_AGE),
    }
    store = draft_store()
    slug = _character_draft_slug(scenario_id)
    rolled_key = rolled_abilities_session_key(scenario_id)
    rolled = st.session_state.get(rolled_key)
    rolled_obj = rolled if isinstance(rolled, RolledAbilities) else None
    if not _character_draft_has_content(fields, default_world=default_world, rolled=rolled_obj):
        store.delete(slug)
        return

    payload: dict = {
        "kind": "character_create",
        "scenario_id": scenario_id,
        "fields": fields,
    }
    if rolled_obj is not None:
        payload["rolled_abilities"] = rolled_abilities_to_dict(rolled_obj)
    store.save(slug, payload)


def clear_character_draft(scenario_id: str) -> None:
    for key in character_draft_keys(scenario_id):
        st.session_state.pop(key, None)
    clear_rolled_abilities(scenario_id)
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


def _reset_invalid_data_editor_state(key: str) -> None:
    """Drop values that are not Streamlit data_editor widget state.

    data_editor expects ``{"edited_rows": ..., "added_rows": ..., "deleted_rows": ...}``.
    Restoring a row list into the same key crashes with
    ``AttributeError: 'list' object has no attribute 'get'``.
    """
    if key not in st.session_state:
        return
    value = st.session_state[key]
    if isinstance(value, dict) and (
        "edited_rows" in value or "added_rows" in value or "deleted_rows" in value
    ):
        return
    st.session_state.pop(key, None)


def init_scenario_editor_draft(scenario, *, creating: bool) -> None:
    seeds = {
        "title": scenario.title,
        "description": scenario.description,
        "world_id": scenario.world_id,
        "world": scenario.world,
        "tone": scenario.tone,
        "opening_scene_name": scenario.opening_scene_name,
        "opening_prompt": scenario.opening_prompt,
        "custom_world_overlay": scenario.custom_world_overlay,
    }
    for field, default in seeds.items():
        seed_widget(
            scenario_editor_field_key(scenario.id, creating, field),
            default,
        )

    for key in scenario_editor_table_keys(scenario.id, creating):
        _reset_invalid_data_editor_state(key)


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
