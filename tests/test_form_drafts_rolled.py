from game.character_creation import roll_ability_scores
from ui.form_drafts import (
    get_rolled_abilities,
    restore_character_draft_extras,
    rolled_abilities_session_key,
    sync_character_draft_to_disk,
)


def test_rolled_abilities_isolated_by_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr("game.draft_store.DRAFTS_DIR", tmp_path)
    state = {}

    class FakeState(dict):
        def __getitem__(self, key):
            return state[key]

        def __setitem__(self, key, value):
            state[key] = value

        def __contains__(self, key):
            return key in state

        def get(self, key, default=None):
            return state.get(key, default)

        def pop(self, key, default=None):
            return state.pop(key, default)

    fake = FakeState()
    import ui.form_drafts as drafts

    original = drafts.st.session_state
    drafts.st.session_state = fake
    try:
        fake["current_profile_id"] = "profile-a"
        rolled_a = get_rolled_abilities("scenario_a", default_factory=roll_ability_scores)
        rolled_b = get_rolled_abilities("scenario_b", default_factory=roll_ability_scores)

        assert rolled_abilities_session_key("scenario_a") in fake
        assert rolled_abilities_session_key("scenario_b") in fake
        assert rolled_a is not rolled_b

        sync_character_draft_to_disk("scenario_a", default_world="fantasy")
        fake.pop(rolled_abilities_session_key("scenario_a"), None)
        restore_character_draft_extras("scenario_a")
        restored = fake[rolled_abilities_session_key("scenario_a")]
        assert restored.total_score() == rolled_a.total_score()
    finally:
        drafts.st.session_state = original
