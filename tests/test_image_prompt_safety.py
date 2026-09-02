from chain.image_prompt_safety import (
    format_content_policy_hint,
    is_content_policy_error,
    sanitize_image_text,
)
from chain.character_portrait import build_portrait_prompt
from game.models import Character
from game.profile import CharacterCard
from game.appearance import CharacterAppearance


def test_is_content_policy_error():
    err = "InputTextSensitiveContentDetected.PolicyViolation: copyright"
    assert is_content_policy_error(err)


def test_sanitize_removes_ip_terms():
    text = sanitize_image_text("雾港调查员，曾追踪哈利波特相关案件")
    assert "哈利波特" not in text
    assert "雾港调查员" in text


def test_safe_portrait_prompt_omits_career_hints():
    card = CharacterCard.from_character(Character(name="艾拉", background="边境佣兵"))
    card.campaign_history = []
    card.notable_facts = ["曾见过钢铁侠"]
    normal = build_portrait_prompt(card, safe_mode=False)
    safe = build_portrait_prompt(card, safe_mode=True)
    assert "钢铁侠" not in safe
    assert "原创角色" in safe
    assert "非现有" in safe


def test_format_content_policy_hint():
    hint = format_content_policy_hint("PolicyViolation")
    assert "版权" in hint
