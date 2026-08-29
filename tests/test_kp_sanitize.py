from game.kp_sanitize import sanitize_kp_narrative


def test_sanitize_replaces_pure_high_risk_response():
    assert "high risk" not in sanitize_kp_narrative("high risk content blocked").lower()
    assert "重试" in sanitize_kp_narrative("high risk")


def test_sanitize_strips_artifact_lines_keeps_story():
    raw = "你挥剑劈中对方。\nhigh risk moderation flagged\n血溅在墙上。"
    cleaned = sanitize_kp_narrative(raw)
    assert "high risk" not in cleaned.lower()
    assert "你挥剑劈中对方" in cleaned
    assert "血溅在墙上" in cleaned
