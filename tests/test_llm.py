import os
from unittest.mock import patch

from chain.llm import build_chat_openai_kwargs


@patch.dict(os.environ, {"LLM_THINKING_ENABLED": "false"}, clear=False)
def test_thinking_disabled_by_default():
    from config.settings import get_settings

    get_settings.cache_clear()
    kwargs = build_chat_openai_kwargs()
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


@patch.dict(os.environ, {"LLM_THINKING_ENABLED": "true"}, clear=False)
def test_thinking_enabled_when_configured():
    from config.settings import get_settings

    get_settings.cache_clear()
    kwargs = build_chat_openai_kwargs()
    assert "extra_body" not in kwargs
