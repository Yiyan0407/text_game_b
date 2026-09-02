from unittest.mock import MagicMock, patch

from chain.image_prompt_safety import (
    format_content_policy_hint,
    format_image_generation_error,
    is_content_policy_error,
    sanitize_image_text,
)
from chain.scene_image import ImageGenerationResult
from chain.character_portrait import build_portrait_prompt
from game.models import Character
from game.profile import CharacterCard
from game.appearance import CharacterAppearance


def test_is_content_policy_error():
    err = "InputTextSensitiveContentDetected.PolicyViolation: copyright"
    assert is_content_policy_error(err)


def test_is_output_policy_error():
    from chain.image_prompt_safety import is_output_policy_error

    err = "OutputImageSensitiveContentDetected: sensitive information"
    assert is_output_policy_error(err)
    assert is_content_policy_error(err)


def test_sanitize_removes_ip_terms():
    text = sanitize_image_text("雾港调查员，曾追踪哈利波特相关案件")
    assert "哈利波特" not in text
    assert "雾港调查员" in text


def test_safe_portrait_prompt_keeps_style_and_strips_risky_text():
    card = CharacterCard.from_character(Character(name="艾拉", background="边境佣兵"))
    card.campaign_history = []
    card.notable_facts = ["曾见过钢铁侠"]
    card.equipment = []
    normal = build_portrait_prompt(card, safe_mode=False)
    safe = build_portrait_prompt(card, safe_mode=True)
    assert "钢铁侠" not in safe
    assert "近期经历" not in safe
    assert "写实" in safe
    assert "摄影" in safe
    assert "写实风格" in safe
    assert "原创角色" not in safe
    assert "角色称呼" not in safe
    assert "边境佣兵" in safe
    assert "写实" in normal


def test_format_content_policy_hint():
    hint = format_content_policy_hint("OutputImageSensitiveContentDetected")
    assert "生成的图片" in hint
    assert "AI 矫正" in hint


def test_format_image_generation_error_avoids_double_wrap():
    raw = "OutputImageSensitiveContentDetected"
    once = format_image_generation_error(raw)
    twice = format_image_generation_error(once)
    assert once == twice
    assert once.count("系统已自动尝试") == 1


@patch("chain.scene_image._generate_seedream")
def test_policy_fallback_retries_with_llm_refined_prompt(mock_generate):
    from chain.scene_image import generate_with_policy_fallback

    policy_err = ImageGenerationResult(error="OutputImageSensitiveContentDetected")
    ok = ImageGenerationResult(url="https://example.com/refined.jpg")
    mock_generate.side_effect = [policy_err, policy_err, ok]

    settings = MagicMock()
    settings.seedream_api_key = "key"

    with patch("chain.image_prompt_refiner.ImagePromptRefiner") as refiner_cls:
        refiner_cls.return_value.refine.return_value = "矫正后的写实 prompt"
        result = generate_with_policy_fallback(
            primary_prompt="原始 prompt",
            fallback_prompt="清洗 prompt",
            provider="seedream",
            settings=settings,
            image_kind="portrait",
        )

    assert result.ok
    assert mock_generate.call_count == 3
    refiner_cls.return_value.refine.assert_called_once()
