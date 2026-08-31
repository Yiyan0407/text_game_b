"""应用日志：内存环形缓冲 + 滚动文件，供 /debug 页面与终端查看。"""

from __future__ import annotations

import logging
import sys
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock

from config.settings import LOG_FILE, get_settings

_CONFIGURED = False
_BUFFER_LOCK = Lock()
_LOG_BUFFER: deque[dict[str, str]] = deque(maxlen=3000)

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RingBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            formatter = self.formatter or logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
            entry = {
                "time": formatter.formatTime(record, _DATE_FORMAT),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "text": formatter.format(record),
            }
            with _BUFFER_LOCK:
                _LOG_BUFFER.append(entry)
        except Exception:
            self.handleError(record)


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    buffer_handler = RingBufferHandler()
    buffer_handler.setLevel(level)
    buffer_handler.setFormatter(formatter)
    root.addHandler(buffer_handler)

    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger(__name__).info("日志已初始化 level=%s file=%s", settings.log_level, log_path)


def get_log_buffer_snapshot(*, level: str | None = None, limit: int = 500) -> list[dict[str, str]]:
    with _BUFFER_LOCK:
        rows = list(_LOG_BUFFER)
    if level and level != "ALL":
        rows = [row for row in rows if row["level"] == level]
    return rows[-limit:]


def clear_log_buffer() -> None:
    with _BUFFER_LOCK:
        _LOG_BUFFER.clear()


def tail_log_file(*, lines: int = 400) -> str:
    path = Path(LOG_FILE)
    if not path.is_file():
        return "（尚无日志文件）"
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"（读取日志文件失败：{exc}）"
    rows = content.splitlines()
    if len(rows) <= lines:
        return content
    return "\n".join(rows[-lines:])


def log_file_path() -> Path:
    return Path(LOG_FILE)
