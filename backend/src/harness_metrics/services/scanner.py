import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from harness_metrics.database import Database
from harness_metrics.providers import ProviderAdapter
from harness_metrics.providers.base import UsageEvent
from harness_metrics.providers.claude_trace import parse_claude_trace
from harness_metrics.providers.codex_trace import parse_codex_trace
from harness_metrics.providers.provider_traces import (
    parse_antigravity_trace,
    parse_cursor_trace,
    parse_kiro_trace,
    parse_opencode_trace,
)

logger = logging.getLogger(__name__)

# Sources without per-record timestamps (Cursor transcripts) are stamped with
# the file's mtime and flagged with this metadata value. Their first-seen time
# is kept on later scans so an old turn does not drift forward to "now".
FILE_MTIME = "file-mtime"

USAGE_UPSERT = """INSERT INTO usage_events
(id, provider, session_id, project_path, model, occurred_at,
 input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
 cost_usd, duration_ms, tool_calls, metadata)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
session_id = COALESCE(excluded.session_id, usage_events.session_id),
project_path = COALESCE(excluded.project_path, usage_events.project_path),
model = COALESCE(excluded.model, usage_events.model),
occurred_at = CASE
    WHEN json_extract(excluded.metadata, '$.timestamp_source') = 'file-mtime' THEN usage_events.occurred_at
    ELSE MAX(usage_events.occurred_at, excluded.occurred_at)
END,
input_tokens = MAX(usage_events.input_tokens, excluded.input_tokens),
output_tokens = MAX(usage_events.output_tokens, excluded.output_tokens),
cache_read_tokens = MAX(usage_events.cache_read_tokens, excluded.cache_read_tokens),
cache_write_tokens = MAX(usage_events.cache_write_tokens, excluded.cache_write_tokens),
cost_usd = excluded.cost_usd,
duration_ms = excluded.duration_ms,
tool_calls = excluded.tool_calls,
metadata = excluded.metadata"""

TRACE_UPSERT = """INSERT INTO trace_events
(id, provider, session_id, project_path, model, occurred_at, kind,
 role, name, content, input_tokens, output_tokens, cache_read_tokens,
 cache_write_tokens, metadata)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET model=COALESCE(excluded.model, trace_events.model),
occurred_at = CASE
    WHEN json_extract(excluded.metadata, '$.timestamp_source') = 'file-mtime' THEN trace_events.occurred_at
    ELSE excluded.occurred_at
END,
content=excluded.content,
input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
cache_read_tokens=excluded.cache_read_tokens,
cache_write_tokens=excluded.cache_write_tokens, metadata=excluded.metadata"""


class UsageScanner:
    def __init__(self, database: Database, providers: list[ProviderAdapter]):
        self.database = database
        self.providers = providers
        self._scan_lock = threading.Lock()
        self._last_finished = 0.0
        self._last_counts: dict[str, int] = {}

    def scan(self, max_age: float = 0) -> dict[str, int]:
        """Import new source data.

        ``max_age`` (seconds) lets frequent callers such as polling endpoints
        reuse a scan that finished recently instead of walking every source
        again. The default always scans.
        """
        with self._scan_lock:
            if max_age > 0 and self._last_finished and time.monotonic() - self._last_finished < max_age:
                return self._last_counts
            counts = self._scan()
            self._last_counts, self._last_finished = counts, time.monotonic()
            return counts

    def _retention_cutoff(self) -> str | None:
        days = self.database.setting("trace_retention_days", 0)
        if not isinstance(days, int) or isinstance(days, bool) or days <= 0:
            return None
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    @staticmethod
    def _trace_events(provider: ProviderAdapter, path: Path) -> Iterable[dict[str, Any]]:
        if provider.id == "claude":
            return parse_claude_trace(path, path.parent.name)
        if provider.id == "codex":
            return parse_codex_trace(path)
        if provider.id == "cursor":
            return parse_cursor_trace(path, provider._composer_snapshot(path.stem))  # type: ignore[attr-defined]
        if provider.id == "kiro":
            return parse_kiro_trace(path)
        if provider.id == "opencode":
            return parse_opencode_trace(path, provider._database())  # type: ignore[attr-defined]
        if provider.id == "antigravity":
            return parse_antigravity_trace(path)
        return ()

    @staticmethod
    def _merge_tool_calls(connection: sqlite3.Connection, event: UsageEvent) -> None:
        """Union tool-call ids with the stored row.

        A request whose lines arrive in separate incremental reads would
        otherwise keep only the tool calls of the last read.
        """
        tool_ids = event.metadata.get("tool_use_ids")
        if not tool_ids:
            return
        row = connection.execute("SELECT metadata FROM usage_events WHERE id = ?", (event.id,)).fetchone()
        if row is None:
            return
        try:
            stored = json.loads(row["metadata"]).get("tool_use_ids", [])
        except (json.JSONDecodeError, TypeError, AttributeError):
            stored = []
        merged = list(dict.fromkeys([*(stored if isinstance(stored, list) else []), *tool_ids]))
        event.metadata["tool_use_ids"] = merged
        event.tool_calls = len(merged)

    def _scan(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        cutoff = self._retention_cutoff()
        with self.database.connect() as connection:
            for provider in self.providers:
                imported = 0
                for path in provider.discover():
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    previous = connection.execute(
                        "SELECT size, mtime, state FROM scanned_files WHERE path = ?", (str(path),)
                    ).fetchone()
                    if previous and previous["size"] == stat.st_size and previous["mtime"] == stat.st_mtime:
                        continue
                    try:
                        state = json.loads(previous["state"]) if previous and previous["state"] else {}
                    except (json.JSONDecodeError, TypeError):
                        state = {}
                    file_imported = 0
                    # One unreadable or unexpectedly shaped source must not
                    # abort the scan (and roll back every other provider).
                    connection.execute("SAVEPOINT scan_file")
                    try:
                        incremental = provider.scan_source(path, state if isinstance(state, dict) else {})
                        if incremental is None:
                            usage_events: Iterable[UsageEvent] = provider.parse(path)
                            trace_events = self._trace_events(provider, path)
                            new_state: dict[str, Any] = {}
                        else:
                            usage_events, trace_events, new_state = incremental
                        for event in usage_events:
                            self._merge_tool_calls(connection, event)
                            result = connection.execute(USAGE_UPSERT, (
                                event.id, event.provider, event.session_id, event.project_path,
                                event.model, event.occurred_at, event.input_tokens, event.output_tokens,
                                event.cache_read_tokens, event.cache_write_tokens, event.cost_usd,
                                event.duration_ms, event.tool_calls, json.dumps(event.metadata),
                            ))
                            file_imported += result.rowcount
                        for trace in trace_events:
                            # Transcript text older than the retention window is
                            # not stored; usage totals above are always kept.
                            if cutoff and str(trace["occurred_at"]) < cutoff:
                                continue
                            connection.execute(TRACE_UPSERT, (
                                trace["id"], trace["provider"], trace["session_id"], trace["project_path"],
                                trace["model"], trace["occurred_at"], trace["kind"], trace["role"],
                                trace["name"], trace["content"], trace["input_tokens"],
                                trace["output_tokens"], trace["cache_read_tokens"],
                                trace["cache_write_tokens"], json.dumps(trace["metadata"]),
                            ))
                    except Exception as error:  # noqa: BLE001 - provider data is untrusted
                        if isinstance(error, sqlite3.OperationalError) and "locked" in str(error):
                            raise
                        connection.execute("ROLLBACK TO scan_file")
                        connection.execute("RELEASE scan_file")
                        logger.warning("Skipping %s source %s: %r", provider.id, path, error)
                        continue
                    connection.execute("RELEASE scan_file")
                    imported += file_imported
                    connection.execute(
                        """INSERT INTO scanned_files(path, provider, size, mtime, scanned_at, state)
                        VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET
                        size=excluded.size, mtime=excluded.mtime, scanned_at=excluded.scanned_at,
                        state=excluded.state""",
                        (str(path), provider.id, stat.st_size, stat.st_mtime,
                         datetime.now(timezone.utc).isoformat(), json.dumps(new_state)),
                    )
                counts[provider.id] = imported
            if cutoff:
                connection.execute("DELETE FROM trace_events WHERE occurred_at < ?", (cutoff,))
        return counts
