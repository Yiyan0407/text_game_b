"""ChatOpenAI 工厂：模型分级 + LangChain Runnable 重试（连接/超时/限流）。"""

from __future__ import annotations

import logging

import langchain_core.exceptions as _lc_exc
from langchain_core.runnables.retry import ExponentialJitterParams
from langchain_openai import ChatOpenAI

from config.settings import get_settings

ModelConnectionError = getattr(_lc_exc, "ModelConnectionError", ConnectionError)
ModelRateLimitError = getattr(_lc_exc, "ModelRateLimitError", Exception)
ModelTimeoutError = getattr(_lc_exc, "ModelTimeoutError", TimeoutError)

logger = logging.getLogger(__name__)

LITE_ROLES = frozenset(
    {
        "settlement_router",
        "time_sync",
        "suggestions",
        "scene_map",
    }
)

KP_ROLES = frozenset({"kp"})

# 与 LangChain ModelRetryMiddleware 默认可重试故障对齐（LCEL 链用 with_retry）
LLM_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
    ConnectionError,
    TimeoutError,
    OSError,
)

try:
    from openai import APIConnectionError, APITimeoutError, RateLimitError

    LLM_RETRY_EXCEPTIONS = LLM_RETRY_EXCEPTIONS + (
        APIConnectionError,
        APITimeoutError,
        RateLimitError,
    )
except ImportError:
    pass


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


def _apply_llm_retry(llm: ChatOpenAI) -> ChatOpenAI:
    """为 ChatOpenAI 套上 LangChain RunnableRetry（指数退避 + jitter）。"""
    settings = get_settings()
    if not settings.llm_retry_enabled or settings.llm_max_retries <= 1:
        return llm

    attempts = settings.llm_max_retries
    wrapped = llm.with_retry(
        stop_after_attempt=attempts,
        wait_exponential_jitter=True,
        retry_if_exception_type=LLM_RETRY_EXCEPTIONS,
        exponential_jitter_params=ExponentialJitterParams(
            initial=settings.llm_retry_initial_delay,
            max=settings.llm_retry_max_delay,
            exp_base=settings.llm_retry_backoff_factor,
        ),
    )
    logger.debug(
        "LLM 重试已启用 attempts=%s initial=%ss max=%ss backoff=%s",
        attempts,
        settings.llm_retry_initial_delay,
        settings.llm_retry_max_delay,
        settings.llm_retry_backoff_factor,
    )
    return wrapped  # type: ignore[return-value]


def create_chat_llm(
    *,
    role: str = "default",
    temperature: float | None = None,
    **overrides,
) -> ChatOpenAI:
    llm = ChatOpenAI(
        **build_chat_openai_kwargs(role=role, temperature=temperature, **overrides)
    )
    return _apply_llm_retry(llm)
