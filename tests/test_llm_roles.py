from chain.llm import LITE_ROLES, resolve_model_for_role
from config.settings import get_settings


def test_lite_roles_use_lite_model(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "mimo-v2.5-pro")
    monkeypatch.setenv("OPENAI_MODEL_LITE", "mimo-v2.5")
    get_settings.cache_clear()
    assert resolve_model_for_role("settlement_router") == "mimo-v2.5"
    assert resolve_model_for_role("time_sync") == "mimo-v2.5"
    assert resolve_model_for_role("inventory_sync") == "mimo-v2.5-pro"
    assert resolve_model_for_role("kp") == "mimo-v2.5-pro"
    get_settings.cache_clear()


def test_lite_roles_defined():
    assert "settlement_router" in LITE_ROLES
    assert "time_sync" in LITE_ROLES
