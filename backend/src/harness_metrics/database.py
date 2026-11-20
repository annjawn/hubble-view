import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  session_id TEXT,
  project_path TEXT,
  model TEXT,
  occurred_at TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_write_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  tool_calls INTEGER NOT NULL DEFAULT 0,
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS usage_time_idx ON usage_events(occurred_at);
CREATE INDEX IF NOT EXISTS usage_provider_idx ON usage_events(provider);
CREATE INDEX IF NOT EXISTS usage_project_idx ON usage_events(project_path);
CREATE TABLE IF NOT EXISTS scanned_files (
  path TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  size INTEGER NOT NULL,
  mtime REAL NOT NULL,
  scanned_at TEXT NOT NULL,
  state TEXT
);
CREATE TABLE IF NOT EXISTS trace_events (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  session_id TEXT NOT NULL,
  project_path TEXT,
  model TEXT,
  occurred_at TEXT NOT NULL,
  kind TEXT NOT NULL,
  role TEXT,
  name TEXT,
  content TEXT,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_write_tokens INTEGER NOT NULL DEFAULT 0,
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS trace_session_time_idx ON trace_events(provider, session_id, occurred_at);
CREATE INDEX IF NOT EXISTS trace_provider_time_idx ON trace_events(provider, occurred_at);
CREATE INDEX IF NOT EXISTS trace_time_idx ON trace_events(occurred_at);
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


# Full-text index over transcript text. It is contentless (the text stays in
# trace_events) and kept in step by triggers; `contentless_delete` needs
# SQLite 3.43+ (https://www.sqlite.org/fts5.html#contentless_delete_tables).
# Only the first SEARCH_INDEX_CHARS of an event are indexed so one huge tool
# result cannot dominate the index.
SEARCH_INDEX_CHARS = 20_000
SEARCH_SCHEMA = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS trace_search USING fts5(
  content, name, content='', contentless_delete=1, detail=none
);
CREATE TRIGGER IF NOT EXISTS trace_search_insert AFTER INSERT ON trace_events BEGIN
  INSERT INTO trace_search(rowid, content, name)
  VALUES (new.rowid, substr(new.content, 1, {SEARCH_INDEX_CHARS}), new.name);
END;
CREATE TRIGGER IF NOT EXISTS trace_search_delete AFTER DELETE ON trace_events BEGIN
  DELETE FROM trace_search WHERE rowid = old.rowid;
END;
CREATE TRIGGER IF NOT EXISTS trace_search_update AFTER UPDATE OF content, name ON trace_events
WHEN old.content IS NOT new.content OR old.name IS NOT new.name BEGIN
  DELETE FROM trace_search WHERE rowid = old.rowid;
  INSERT INTO trace_search(rowid, content, name)
  VALUES (new.rowid, substr(new.content, 1, {SEARCH_INDEX_CHARS}), new.name);
END;
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.search_enabled = False

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            # WAL lets API reads proceed while a long scan holds the write
            # transaction. The mode is persistent, so setting it once suffices
            # (https://www.sqlite.org/wal.html).
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(scanned_files)")}
            if "state" not in columns:
                # Per-source resume position for incremental scans.
                connection.execute("ALTER TABLE scanned_files ADD COLUMN state TEXT")
            try:
                connection.executescript(SEARCH_SCHEMA)
                self.search_enabled = True
            except sqlite3.OperationalError:
                # SQLite built without FTS5 or older than 3.43: search falls
                # back to a substring scan.
                self.search_enabled = False
            migration = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'project_path_normalization_v1'"
            ).fetchone()
            if migration is None:
                connection.execute("DELETE FROM scanned_files WHERE provider = 'claude'")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('project_path_normalization_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            root_migration = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'project_root_normalization_v1'"
            ).fetchone()
            if root_migration is None:
                connection.execute("DELETE FROM scanned_files")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('project_root_normalization_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            model_migration = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'codex_model_context_v1'"
            ).fetchone()
            if model_migration is None:
                connection.execute("DELETE FROM scanned_files WHERE provider = 'codex'")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('codex_model_context_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            accounting_migration = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'normalized_token_accounting_v1'"
            ).fetchone()
            if accounting_migration is None:
                connection.execute("DELETE FROM scanned_files")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('normalized_token_accounting_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            kiro_usage_migration = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'kiro_usage_estimator_v1'"
            ).fetchone()
            if kiro_usage_migration is None:
                connection.execute("DELETE FROM usage_events WHERE provider = 'kiro'")
                connection.execute("DELETE FROM scanned_files WHERE provider = 'kiro'")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('kiro_usage_estimator_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            cursor_estimate_migration = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'cursor_context_estimates_v1'"
            ).fetchone()
            if cursor_estimate_migration is None:
                connection.execute("DELETE FROM usage_events WHERE provider = 'cursor'")
                connection.execute("DELETE FROM scanned_files WHERE provider = 'cursor'")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('cursor_context_estimates_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            provider_traces_migration = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'provider_traces_v1'"
            ).fetchone()
            if provider_traces_migration is None:
                connection.execute(
                    "DELETE FROM scanned_files WHERE provider IN ('cursor', 'kiro', 'opencode', 'antigravity')"
                )
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('provider_traces_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            claude_request_migration = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'claude_request_dedup_v1'"
            ).fetchone()
            if claude_request_migration is None:
                connection.execute("DELETE FROM usage_events WHERE provider = 'claude'")
                connection.execute("DELETE FROM scanned_files WHERE provider = 'claude'")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('claude_request_dedup_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            claude_cost_migration = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'claude_api_cost_estimates_v1'"
            ).fetchone()
            if claude_cost_migration is None:
                connection.execute("DELETE FROM usage_events WHERE provider = 'claude'")
                connection.execute("DELETE FROM scanned_files WHERE provider = 'claude'")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('claude_api_cost_estimates_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            remove_cost_estimates = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'remove_claude_cost_estimates_v1'"
            ).fetchone()
            if remove_cost_estimates is None:
                connection.execute("UPDATE usage_events SET cost_usd = 0 WHERE provider = 'claude'")
                connection.execute("DELETE FROM scanned_files WHERE provider = 'claude'")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('remove_claude_cost_estimates_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            trace_capture = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'claude_trace_capture_v1'"
            ).fetchone()
            if trace_capture is None:
                connection.execute("DELETE FROM scanned_files WHERE provider = 'claude'")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('claude_trace_capture_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            codex_trace_capture = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'codex_trace_capture_v1'"
            ).fetchone()
            if codex_trace_capture is None:
                connection.execute("DELETE FROM scanned_files WHERE provider = 'codex'")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('codex_trace_capture_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )
            codex_usage_dedup = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'codex_usage_record_dedup_v1'"
            ).fetchone()
            if codex_usage_dedup is None:
                # Codex rollouts that contain `token_usage_record` lines were
                # imported twice (once more via `token_count`). Drop the
                # duplicate source from the point the new record type appears;
                # the rescan below restores anything still on disk and aligns
                # session ids with the rollout's session_meta id.
                connection.execute(
                    """DELETE FROM usage_events WHERE provider = 'codex'
                    AND json_extract(metadata, '$.type') = 'token_count'
                    AND occurred_at >= (
                        SELECT MIN(occurred_at) FROM usage_events WHERE provider = 'codex'
                        AND json_extract(metadata, '$.type') = 'token_usage_record'
                    )"""
                )
                # Claude tool calls live in message.content blocks and were not
                # counted; a rescan fills usage_events.tool_calls.
                connection.execute("DELETE FROM scanned_files WHERE provider IN ('codex', 'claude')")
                connection.execute(
                    """INSERT INTO app_settings(key, value)
                    VALUES ('codex_usage_record_dedup_v1', 'true')
                    ON CONFLICT(key) DO NOTHING"""
                )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def backfill_search(self, batch: int = 2000) -> int:
        """Index transcript rows stored before the search index existed.

        Runs in small transactions so API reads and settings writes are not
        held up, and records its position so an interrupted run resumes.
        """
        if not self.search_enabled:
            return 0
        position = self.setting("search_backfill_rowid", 0)
        if position == "done":
            return 0
        indexed, position = 0, int(position or 0)
        while True:
            with self.connect() as connection:
                rows = connection.execute(
                    """SELECT rowid, content, name FROM trace_events
                    WHERE rowid > ? AND rowid NOT IN (SELECT rowid FROM trace_search WHERE rowid > ?)
                    ORDER BY rowid LIMIT ?""", (position, position, batch)
                ).fetchall()
                last = connection.execute(
                    "SELECT MAX(rowid) FROM (SELECT rowid FROM trace_events WHERE rowid > ? ORDER BY rowid LIMIT ?)",
                    (position, batch),
                ).fetchone()[0]
                connection.executemany(
                    "INSERT INTO trace_search(rowid, content, name) VALUES (?, ?, ?)",
                    [(row["rowid"], (row["content"] or "")[:SEARCH_INDEX_CHARS], row["name"]) for row in rows],
                )
                indexed += len(rows)
                done = last is None
                connection.execute(
                    "INSERT INTO app_settings(key, value) VALUES('search_backfill_rowid', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (json.dumps("done" if done else last),),
                )
            if done:
                return indexed
            position = last

    def setting(self, key: str, default: object = None) -> object:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value: object) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO app_settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
