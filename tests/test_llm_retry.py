from langchain_core.runnables.retry import RunnableRetry
from langchain_openai import ChatOpenAI

from chain.llm import LLM_RETRY_EXCEPTIONS, create_chat_llm
from config.settings import get_settings


def test_create_chat_llm_wraps_with_retry_when_enabled(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_ENABLED", "true")
    monkeypatch.setenv("LLM_MAX_RETRIES", "4")
    get_settings.cache_clear()
    llm = create_chat_llm()
    assert isinstance(llm, RunnableRetry)


def test_create_chat_llm_skips_retry_when_disabled(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_ENABLED", "false")
    get_settings.cache_clear()
    llm = create_chat_llm()
    assert isinstance(llm, ChatOpenAI)
    assert not isinstance(llm, RunnableRetry)


def test_llm_retry_exception_types_include_connection_errors():
    names = {exc.__name__ for exc in LLM_RETRY_EXCEPTIONS}
    assert "ModelConnectionError" in names
    assert "ConnectionError" in names
