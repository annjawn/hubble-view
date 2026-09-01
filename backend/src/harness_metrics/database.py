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
  scanned_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
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

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

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
