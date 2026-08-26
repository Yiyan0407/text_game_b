from langchain_openai import ChatOpenAI

from config.settings import get_settings


def build_chat_openai_kwargs(*, temperature: float | None = None, **overrides) -> dict:
    settings = get_settings()
    kwargs: dict = {
        "model": settings.openai_model,
        "temperature": settings.llm_temperature if temperature is None else temperature,
        "api_key": settings.openai_api_key or None,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if not settings.llm_thinking_enabled:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    kwargs.update(overrides)
    return kwargs


def create_chat_llm(*, temperature: float | None = None, **overrides) -> ChatOpenAI:
    return ChatOpenAI(**build_chat_openai_kwargs(temperature=temperature, **overrides))
