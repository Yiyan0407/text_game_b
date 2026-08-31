import logging

from config.logging_setup import (
    clear_log_buffer,
    get_log_buffer_snapshot,
    setup_logging,
    tail_log_file,
)
from config.settings import get_settings


def test_setup_logging_writes_to_buffer(tmp_path, monkeypatch):
    log_file = tmp_path / "test.log"
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    get_settings.cache_clear()
    monkeypatch.setattr("config.logging_setup.LOG_FILE", log_file)
    monkeypatch.setattr("config.logging_setup._CONFIGURED", False)

    setup_logging()
    clear_log_buffer()
    logging.getLogger("test.logging").info("hello debug")

    rows = get_log_buffer_snapshot(limit=10)
    assert any("hello debug" in row["message"] for row in rows)
    assert "hello debug" in tail_log_file(lines=10)
