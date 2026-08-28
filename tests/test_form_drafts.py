from ui.form_drafts import (
    character_draft_keys,
    clear_character_draft,
    init_character_draft,
    init_scenario_editor_draft,
    scenario_editor_field_key,
    scenario_editor_table_keys,
)
from game.scenario import Scenario


def test_character_draft_keys():
    name_key, background_key, world_key = character_draft_keys("missing_fishermen")
    assert name_key.endswith("_name")
    assert background_key.endswith("_background")
    assert world_key.endswith("_world")


def test_init_and_clear_character_draft():
    state = {}
    name_key, background_key, world_key = character_draft_keys("test_scenario")

    class FakeState(dict):
        def __getitem__(self, key):
            return state[key]

        def __setitem__(self, key, value):
            state[key] = value

        def __contains__(self, key):
            return key in state

        def pop(self, key, default=None):
            return state.pop(key, default)

    fake = FakeState()
    import ui.form_drafts as drafts

    original = drafts.st.session_state
    drafts.st.session_state = fake
    try:
        init_character_draft("test_scenario", "fantasy")
        assert fake[name_key] == ""
        assert fake[background_key] == ""
        assert fake[world_key] == "fantasy"

        fake[name_key] = "艾拉"
        clear_character_draft("test_scenario")
        assert name_key not in fake
    finally:
        drafts.st.session_state = original


def test_scenario_editor_field_key():
    key = scenario_editor_field_key("draft_manual", True, "title")
    assert key == "scenario_edit_title_draft_manual_1"


def test_init_scenario_editor_draft_seeds_once():
    state = {}
    scenario = Scenario(id="draft_manual", title="测试标题")

    class FakeState(dict):
        def __getitem__(self, key):
            return state[key]

        def __setitem__(self, key, value):
            state[key] = value

        def __contains__(self, key):
            return key in state

        def pop(self, key, default=None):
            return state.pop(key, default)

    fake = FakeState()
    import ui.form_drafts as drafts

    original = drafts.st.session_state
    drafts.st.session_state = fake
    try:
        init_scenario_editor_draft(scenario, creating=True)
        title_key = scenario_editor_field_key("draft_manual", True, "title")
        quests_key, nodes_key, endings_key = scenario_editor_table_keys("draft_manual", True)
        assert fake[title_key] == "测试标题"
        assert quests_key not in fake
        assert nodes_key not in fake
        assert endings_key not in fake

        fake[title_key] = "用户修改"
        init_scenario_editor_draft(scenario, creating=True)
        assert fake[title_key] == "用户修改"
    finally:
        drafts.st.session_state = original


def test_init_scenario_editor_drops_list_data_editor_state():
    state = {}
    scenario = Scenario(id="draft_manual", title="测试标题")

    class FakeState(dict):
        def __getitem__(self, key):
            return state[key]

        def __setitem__(self, key, value):
            state[key] = value

        def __contains__(self, key):
            return key in state

        def pop(self, key, default=None):
            return state.pop(key, default)

    fake = FakeState()
    import ui.form_drafts as drafts

    original = drafts.st.session_state
    drafts.st.session_state = fake
    try:
        quests_key, nodes_key, endings_key = scenario_editor_table_keys("draft_manual", True)
        fake[quests_key] = [{"id": "q1", "title": "坏数据"}]
        fake[nodes_key] = {"edited_rows": {}, "added_rows": [], "deleted_rows": []}
        init_scenario_editor_draft(scenario, creating=True)
        assert quests_key not in fake
        assert nodes_key in fake
        assert endings_key not in fake
    finally:
        drafts.st.session_state = original
