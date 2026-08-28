from ui.risky_action import (
    CANCEL_BUTTON_KEY,
    CONFIRM_BUTTON_KEY,
    SESSION_KEY,
)


def test_risky_action_keys_do_not_overlap_button_widgets():
    assert SESSION_KEY != CONFIRM_BUTTON_KEY
    assert SESSION_KEY != CANCEL_BUTTON_KEY
    assert CONFIRM_BUTTON_KEY == "risky_action_confirm"
    assert SESSION_KEY == "risky_action_pending"
