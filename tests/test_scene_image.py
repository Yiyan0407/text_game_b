from unittest.mock import MagicMock, patch

from chain.scene_image import ImageGenerationResult, _build_prompt, generate_scene_image


def test_build_prompt_chinese():
    text = _build_prompt("灰港码头", "赛博朋克", "雨夜")
    assert "灰港码头" in text
    assert "赛博朋克" in text


@patch("chain.scene_image.generate_with_policy_fallback")
@patch("chain.scene_image.get_settings")
def test_generate_uses_seedream(mock_settings, mock_fallback):
    settings = MagicMock()
    settings.enable_scene_images = True
    settings.image_provider = "seedream"
    mock_settings.return_value = settings
    mock_fallback.return_value = ImageGenerationResult(url="https://example.com/img.png")

    result = generate_scene_image("场景", "世界", "基调")
    assert result.url == "https://example.com/img.png"
    mock_fallback.assert_called_once()


@patch("chain.scene_image.httpx.Client")
@patch("chain.scene_image.get_settings")
def test_seedream_api_call(mock_settings, mock_client_cls):
    settings = MagicMock()
    settings.seedream_api_key = "test-key"
    settings.seedream_base_url = "https://ark.cn-beijing.volces.com/api/v3"
    settings.seedream_model = "doubao-seedream-4-5-251128"
    settings.seedream_size = "2K"
    settings.seedream_watermark = False
    mock_settings.return_value = settings

    mock_response = MagicMock()
    mock_response.is_error = False
    mock_response.json.return_value = {"data": [{"url": "https://img.test/1.jpg"}]}
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value = mock_client

    from chain.scene_image import _generate_seedream

    result = _generate_seedream("测试 prompt", settings)
    assert result.url == "https://img.test/1.jpg"
    call_kwargs = mock_client.post.call_args
    assert "images/generations" in call_kwargs[0][0]
    assert call_kwargs[1]["json"]["model"] == "doubao-seedream-4-5-251128"


@patch("chain.scene_image.httpx.Client")
@patch("chain.scene_image.get_settings")
def test_seedream_surfaces_api_error(mock_settings, mock_client_cls):
    settings = MagicMock()
    settings.seedream_api_key = "test-key"
    settings.seedream_base_url = "https://ark.cn-beijing.volces.com/api/v3"
    settings.seedream_model = "doubao-seedream-4-5-251128"
    settings.seedream_size = "2K"
    settings.seedream_watermark = False
    mock_settings.return_value = settings

    mock_response = MagicMock()
    mock_response.is_error = True
    mock_response.status_code = 404
    mock_response.text = '{"error":{"code":"ModelNotOpen","message":"model not activated"}}'
    mock_response.json.return_value = {
        "error": {"code": "ModelNotOpen", "message": "model not activated"}
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value = mock_client

    from chain.scene_image import _generate_seedream

    result = _generate_seedream("测试 prompt", settings)
    assert result.url is None
    assert "ModelNotOpen" in result.error
