import json
import threading
from datetime import datetime, timezone

from harness_metrics.database import Database
from harness_metrics.providers import ProviderAdapter
from harness_metrics.providers.claude_trace import parse_claude_trace
from harness_metrics.providers.codex_trace import parse_codex_trace
from harness_metrics.providers.provider_traces import (
    parse_antigravity_trace, parse_cursor_trace, parse_kiro_trace, parse_opencode_trace,
)


class UsageScanner:
    def __init__(self, database: Database, providers: list[ProviderAdapter]):
        self.database = database
        self.providers = providers
        self._scan_lock = threading.Lock()

    def scan(self) -> dict[str, int]:
        with self._scan_lock:
            return self._scan()

    def _scan(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self.database.connect() as connection:
            for provider in self.providers:
                imported = 0
                for path in provider.discover():
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    previous = connection.execute(
                        "SELECT size, mtime FROM scanned_files WHERE path = ?", (str(path),)
                    ).fetchone()
                    if previous and previous["size"] == stat.st_size and previous["mtime"] == stat.st_mtime:
                        continue
                    for event in provider.parse(path):
                        result = connection.execute(
                            """INSERT OR IGNORE INTO usage_events
                            (id, provider, session_id, project_path, model, occurred_at,
                             input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                             cost_usd, duration_ms, tool_calls, metadata)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                            project_path = CASE
                                WHEN excluded.project_path IS NOT NULL THEN excluded.project_path
                                ELSE usage_events.project_path
                            END,
                            model = CASE
                                WHEN excluded.model IS NOT NULL THEN excluded.model
                                ELSE usage_events.model
                            END,
                            occurred_at = MAX(usage_events.occurred_at, excluded.occurred_at),
                            input_tokens = MAX(usage_events.input_tokens, excluded.input_tokens),
                            output_tokens = MAX(usage_events.output_tokens, excluded.output_tokens),
                            cache_read_tokens = MAX(usage_events.cache_read_tokens, excluded.cache_read_tokens),
                            cache_write_tokens = MAX(usage_events.cache_write_tokens, excluded.cache_write_tokens),
                            cost_usd = excluded.cost_usd,
                            duration_ms = excluded.duration_ms,
                            tool_calls = excluded.tool_calls,
                            metadata = excluded.metadata""",
                            (
                                event.id, event.provider, event.session_id, event.project_path,
                                event.model, event.occurred_at, event.input_tokens, event.output_tokens,
                                event.cache_read_tokens, event.cache_write_tokens, event.cost_usd,
                                event.duration_ms, event.tool_calls, json.dumps(event.metadata),
                            ),
                        )
                        imported += result.rowcount
                    trace_events = (
                        parse_claude_trace(path, path.parent.name) if provider.id == "claude"
                        else parse_codex_trace(path) if provider.id == "codex"
                        else parse_cursor_trace(path, provider._composer_snapshot(path.stem)) if provider.id == "cursor"
                        else parse_kiro_trace(path) if provider.id == "kiro"
                        else parse_opencode_trace(path, provider._database()) if provider.id == "opencode"
                        else parse_antigravity_trace(path) if provider.id == "antigravity"
                        else ()
                    )
                    for event in trace_events:
                        connection.execute(
                            """INSERT INTO trace_events
                            (id, provider, session_id, project_path, model, occurred_at, kind,
                             role, name, content, input_tokens, output_tokens, cache_read_tokens,
                             cache_write_tokens, metadata)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET model=COALESCE(excluded.model, trace_events.model),
                            occurred_at=excluded.occurred_at, content=excluded.content,
                            input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
                            cache_read_tokens=excluded.cache_read_tokens,
                            cache_write_tokens=excluded.cache_write_tokens, metadata=excluded.metadata""",
                            (event["id"], event["provider"], event["session_id"], event["project_path"],
                             event["model"], event["occurred_at"], event["kind"], event["role"],
                             event["name"], event["content"], event["input_tokens"],
                             event["output_tokens"], event["cache_read_tokens"],
                             event["cache_write_tokens"], json.dumps(event["metadata"])),
                        )
                    connection.execute(
                        """INSERT INTO scanned_files(path, provider, size, mtime, scanned_at)
                        VALUES (?, ?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET
                        size=excluded.size, mtime=excluded.mtime, scanned_at=excluded.scanned_at""",
                        (str(path), provider.id, stat.st_size, stat.st_mtime, datetime.now(timezone.utc).isoformat()),
                    )
                counts[provider.id] = imported
        return counts
