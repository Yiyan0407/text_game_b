from langchain_openai import ChatOpenAI

from config.settings import get_settings

LITE_ROLES = frozenset(
    {
        "settlement_router",
        "time_sync",
        "suggestions",
        "scene_map",
    }
)

KP_ROLES = frozenset({"kp"})


def resolve_model_for_role(role: str) -> str:
    settings = get_settings()
    if role in LITE_ROLES:
        return settings.openai_model_lite
    if role in KP_ROLES:
        return settings.openai_model_kp
    return settings.openai_model


def build_chat_openai_kwargs(
    *,
    role: str = "default",
    temperature: float | None = None,
    **overrides,
) -> dict:
    settings = get_settings()
    model = overrides.pop("model", None) or resolve_model_for_role(role)
    kwargs: dict = {
        "model": model,
        "temperature": settings.llm_temperature if temperature is None else temperature,
        "api_key": settings.openai_api_key or None,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if not settings.llm_thinking_enabled:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    kwargs.update(overrides)
    return kwargs


def create_chat_llm(
    *,
    role: str = "default",
    temperature: float | None = None,
    **overrides,
) -> ChatOpenAI:
    return ChatOpenAI(
        **build_chat_openai_kwargs(role=role, temperature=temperature, **overrides)
    )
