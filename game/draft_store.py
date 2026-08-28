"""将未提交的 UI 草稿持久化到本地磁盘（按玩家档案分目录）。"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config.settings import DATA_DIR

DRAFTS_DIR = DATA_DIR / "drafts"


class DraftStore:
    def __init__(self, scope: str):
        self.scope = scope or "_guest"
        self.dir = DRAFTS_DIR / self.scope
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, slug: str) -> Path:
        safe = slug.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self.dir / f"{safe}.json"

    def load(self, slug: str) -> dict | None:
        path = self._path(slug)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return payload if isinstance(payload, dict) else None

    def save(self, slug: str, payload: dict) -> None:
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        path = self._path(slug)
        content = json.dumps(data, ensure_ascii=False, indent=2)
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=self.dir,
                prefix=f".{path.stem}-",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            tmp_path = None
        except Exception:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

    def delete(self, slug: str) -> None:
        path = self._path(slug)
        if path.exists():
            path.unlink()
