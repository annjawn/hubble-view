import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .base import ProviderAdapter, UsageEvent
from .jsonl import _project_root


def _integer(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


class OpenCodeAdapter(ProviderAdapter):
    id = "opencode"
    name = "OpenCode"

    @staticmethod
    def _database() -> Path:
        override = os.environ.get("OPENCODE_DB")
        return Path(override).expanduser() if override else Path.home() / ".local" / "share" / "opencode" / "opencode.db"

    def log_roots(self) -> list[Path]:
        return [self._database()]

    def discover(self) -> Iterable[Path]:
        database = self._database()
        wal = Path(f"{database}-wal")
        # The WAL changes immediately while OpenCode is running; the main DB
        # may retain an old mtime until a checkpoint occurs.
        if wal.exists():
            yield wal
        elif database.exists():
            yield database

    def parse(self, path: Path) -> Iterable[UsageEvent]:
        database = self._database()
        if not database.exists():
            return
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT m.id, m.session_id, m.time_created, m.time_updated, m.data,
                    s.directory,
                    (SELECT COUNT(*) FROM part p
                     WHERE p.message_id = m.id AND json_extract(p.data, '$.type') = 'tool') tool_calls
                FROM message m JOIN session s ON s.id = m.session_id
                WHERE json_extract(m.data, '$.role') = 'assistant'"""
            ).fetchall()
            connection.close()
        except sqlite3.Error:
            return

        for row in rows:
            try:
                data = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
            cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
            input_tokens = _integer(tokens.get("input"))
            output_tokens = _integer(tokens.get("output"))
            reasoning_tokens = _integer(tokens.get("reasoning"))
            cache_read = _integer(cache.get("read"))
            cache_write = _integer(cache.get("write"))
            if not any((input_tokens, output_tokens, reasoning_tokens, cache_read, cache_write, row["tool_calls"])):
                continue
            time_data = data.get("time") if isinstance(data.get("time"), dict) else {}
            timestamp_ms = time_data.get("completed") or time_data.get("created") or row["time_updated"] or row["time_created"]
            occurred_at = datetime.fromtimestamp(float(timestamp_ms) / 1000, timezone.utc).isoformat()
            created_ms = time_data.get("created")
            completed_ms = time_data.get("completed")
            duration_ms = max(0, _integer(completed_ms) - _integer(created_ms)) if created_ms and completed_ms else 0
            provider_id = data.get("providerID")
            model_id = data.get("modelID")
            model = str(model_id) if model_id else None
            raw_id = f"opencode:message:{row['id']}"
            yield UsageEvent(
                id=hashlib.sha256(raw_id.encode()).hexdigest(),
                provider=self.id,
                occurred_at=occurred_at,
                session_id=str(row["session_id"]),
                project_path=_project_root(row["directory"]),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens + reasoning_tokens,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                cost_usd=float(data.get("cost", 0) or 0),
                duration_ms=duration_ms,
                tool_calls=int(row["tool_calls"] or 0),
                metadata={
                    "type": "assistant",
                    "model_provider": str(provider_id) if provider_id else None,
                    "reasoning_tokens": reasoning_tokens,
                    "usage_source": "opencode-db",
                },
            )
