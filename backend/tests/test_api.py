import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from harness_metrics.config import Settings
from harness_metrics.database import Database
from harness_metrics.main import create_app
from harness_metrics.providers.base import ProviderAdapter
from harness_metrics.services.artifacts import ArtifactService


class EmptyClaudeAdapter(ProviderAdapter):
    id = "claude"
    name = "Claude Code"
    def log_roots(self): return []
    def discover(self): return []
    def parse(self, path): return []


def test_health_and_empty_overview(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        overview = client.get("/api/overview").json()
        assert overview["totals"]["total_tokens"] == 0
        assert overview["projects"] == []
        assert overview["models"] == []
        assert [window["provider"] for window in overview["windows"]] == ["claude", "codex", None]
        assert overview["windows"][0]["active"] is False


def test_settings_round_trip(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    with TestClient(app) as client:
        response = client.patch("/api/settings", json={"scan_interval_seconds": 45})
        assert response.status_code == 200
        assert response.json()["scan_interval_seconds"] == 45


def test_projects_are_unlimited_and_encoded_aliases_are_merged(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    now = datetime.now(timezone.utc).isoformat()
    with TestClient(app) as client:
        with app.state.database.connect() as connection:
            for index in range(12):
                connection.execute(
                    """INSERT INTO usage_events
                    (id, provider, session_id, project_path, occurred_at, input_tokens)
                    VALUES (?, 'codex', ?, ?, ?, 100)""",
                    (f"event-{index}", f"session-{index}", f"/tmp/project-{index}", now),
                )
            connection.execute(
                """INSERT INTO usage_events
                (id, provider, session_id, project_path, occurred_at, input_tokens)
                VALUES ('encoded-alias', 'claude', 'alias-session', '-tmp-project-0', ?, 50)""",
                (now,),
            )
        projects = client.get("/api/overview?days=30").json()["projects"]
        assert len(projects) == 12
        merged = next(project for project in projects if project["project_path"] == "/tmp/project-0")
        assert merged["tokens"] == 150


def test_overview_aggregates_usage_by_provider_and_model(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    now = datetime.now(timezone.utc).isoformat()
    with TestClient(app) as client:
        with app.state.database.connect() as connection:
            connection.executemany(
                """INSERT INTO usage_events
                (id, provider, session_id, model, occurred_at, input_tokens,
                 output_tokens, cache_read_tokens, cache_write_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    ("one", "claude", "session-1", "claude-sonnet", now, 10, 5, 100, 20),
                    ("two", "claude", "session-2", "claude-sonnet", now, 20, 7, 200, 30),
                    ("three", "codex", "session-3", "gpt-5.6", now, 40, 8, 300, 0),
                ],
            )
        models = client.get("/api/overview?days=30").json()["models"]
        assert [(item["provider"], item["model"]) for item in models] == [
            ("claude", "claude-sonnet"), ("codex", "gpt-5.6")
        ]
        claude = models[0]
        assert (claude["tokens"], claude["sessions"]) == (392, 2)


def test_provider_session_and_trace_endpoints(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[EmptyClaudeAdapter()])
    now = datetime.now(timezone.utc).isoformat()
    with TestClient(app) as client:
        with app.state.database.connect() as connection:
            connection.execute(
                """INSERT INTO trace_events
                (id, provider, session_id, project_path, model, occurred_at, kind, role,
                 content, input_tokens, output_tokens)
                VALUES ('trace-1', 'claude', 'session-1', '/tmp/project', 'claude-test', ?,
                        'message', 'assistant', 'Done', 10, 4)""", (now,)
            )
        sessions = client.get("/api/providers/claude/sessions").json()
        assert sessions[0]["status"] == "live"
        assert sessions[0]["total_tokens"] == 14
        events = client.get("/api/providers/claude/sessions/session-1/events").json()
        assert events[0]["content"] == "Done"


def test_artifacts_include_global_and_project_files_and_redact_secrets(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    (home / ".claude").mkdir(parents=True)
    (project / ".claude" / "rules").mkdir(parents=True)
    # Claude Code replaces every non-alphanumeric path character with "-".
    encoded_project = re.sub(r"[^A-Za-z0-9]", "-", str(project))
    auto_memory = home / ".claude" / "projects" / encoded_project / "memory"
    auto_memory.mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{"apiKey":"private", "theme":"dark"}')
    (home / ".claude" / "CLAUDE.md").write_text("Global guidance")
    (project / "CLAUDE.md").write_text("Project guidance")
    (project / ".claude" / "rules" / "tests.md").write_text("Always test")
    (auto_memory / "debugging.md").write_text("Recurring debugging breakthrough")
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[EmptyClaudeAdapter()])
    with TestClient(app) as client:
        app.state.artifacts = ArtifactService(app.state.database, home)
        with app.state.database.connect() as connection:
            connection.execute(
                """INSERT INTO usage_events(id, provider, session_id, project_path, occurred_at)
                VALUES ('one', 'claude', 'session', ?, ?)""",
                (str(project), datetime.now(timezone.utc).isoformat()),
            )
        global_response = client.get("/api/providers/claude/artifacts")
        assert global_response.status_code == 200
        global_artifacts = global_response.json()["artifacts"]
        assert {(item["scope"], item["name"]) for item in global_artifacts} >= {
            ("global", "CLAUDE.md"), ("global", "settings.json")
        }
        assert any(item["category"] == "memory" and item["name"] == "CLAUDE.md" for item in global_artifacts)
        assert not any(item["category"] == "instructions" for item in global_artifacts)
        assert all(item["scope"] == "global" for item in global_artifacts)
        project_response = client.get("/api/projects/artifacts", params={"project_path": str(project)})
        assert project_response.status_code == 200
        project_artifacts = project_response.json()["artifacts"]
        assert {(item["scope"], item["name"]) for item in project_artifacts} >= {
            ("project", "CLAUDE.md"), ("project", "tests.md"), ("project", "debugging.md")
        }
        assert any(item["category"] == "memory" and item["name"] == "debugging.md" for item in project_artifacts)
        assert all(item["scope"] == "project" for item in project_artifacts)
        settings = next(item for item in global_artifacts if item["category"] == "settings")
        assert "private" not in settings["content"]
        assert "dark" in settings["content"]
        assert client.get("/api/projects/artifacts", params={"project_path": str(tmp_path / 'other')}).status_code == 404


def test_provider_sessions_fall_back_to_usage_and_use_repository_root(tmp_path: Path):
    project = tmp_path / "project"
    nested = project / "src" / "feature"
    nested.mkdir(parents=True)
    (project / ".git").mkdir()
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[EmptyClaudeAdapter()])
    now = datetime.now(timezone.utc).isoformat()
    with TestClient(app) as client:
        with app.state.database.connect() as connection:
            connection.execute(
                """INSERT INTO usage_events
                (id, provider, session_id, project_path, model, occurred_at, input_tokens, tool_calls)
                VALUES ('usage-only', 'claude', 'usage-session', ?, 'model', ?, 12, 1)""",
                (str(nested), now),
            )
        session = client.get("/api/providers/claude/sessions").json()[0]
        assert session["project_path"] == str(project)
        assert session["total_tokens"] == 12
        events = client.get("/api/providers/claude/sessions/usage-session/events").json()
        assert events[0]["kind"] == "usage"


def test_global_artifact_patterns_cover_other_providers(tmp_path: Path):
    home = tmp_path / "home"
    files = {
        ".cursor/skills-cursor/review/SKILL.md": "Cursor skill",
        ".kiro/powers/installed.json": "{}",
        ".config/opencode/opencode.jsonc": "{}",
        ".gemini/config/config.json": "{}",
    }
    for relative, content in files.items():
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    service = ArtifactService(Database(tmp_path / "artifacts.db"), home)
    service.database.initialize()
    assert service.global_list("cursor")["artifacts"][0]["category"] == "skills"
    assert service.global_list("kiro")["artifacts"][0]["category"] == "settings"
    assert service.global_list("opencode")["artifacts"][0]["category"] == "settings"
    assert service.global_list("antigravity")["artifacts"][0]["category"] == "settings"


class FailingAdapter(ProviderAdapter):
    id = "codex"
    name = "Codex"

    def __init__(self, source: Path):
        self.source = source

    def log_roots(self): return [self.source]
    def discover(self): return [self.source]
    def parse(self, path): raise AttributeError("unexpected record shape")


def test_api_token_is_required_when_configured(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, database_path=tmp_path / "test.db", api_token="launch-token")
    with TestClient(create_app(settings, adapters=[])) as client:
        assert client.get("/api/overview").status_code == 401
        assert client.get("/api/overview", headers={"X-Hubble-Token": "wrong"}).status_code == 401
        assert client.get("/api/overview", headers={"X-Hubble-Token": "launch-token"}).status_code == 200


def test_scan_survives_a_failing_source(tmp_path: Path):
    source = tmp_path / "broken.jsonl"
    source.write_text("{}")
    app = create_app(
        Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[FailingAdapter(source)]
    )
    with TestClient(app) as client:
        assert client.post("/api/scan").json() == {"imported": {"codex": 0}}
        assert "initial_scan_complete" in client.get("/api/health").json()


def test_session_events_return_the_latest_events_in_order(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    with TestClient(app) as client:
        with app.state.database.connect() as connection:
            connection.executemany(
                """INSERT INTO trace_events(id, provider, session_id, occurred_at, kind, content)
                VALUES (?, 'claude', 'long', ?, 'message', ?)""",
                [(f"event-{index}", f"2026-08-31T00:00:{index:02d}Z", str(index)) for index in range(5)],
            )
        events = client.get("/api/providers/claude/sessions/long/events?limit=2").json()
        assert [event["content"] for event in events] == ["3", "4"]


def test_redaction_masks_tokens_but_keeps_token_limits(tmp_path: Path):
    from harness_metrics.services.artifacts import _redact

    redacted = _redact(
        '{"env": {"GITHUB_TOKEN": "value-one"}, "max_tokens": 4096,'
        ' "headers": {"Authorization": "value-two"}}', ".json",
    )
    assert "value-one" not in redacted and "value-two" not in redacted
    assert "4096" in redacted
    assert 'GITHUB_TOKEN = "••••••••"' in _redact('GITHUB_TOKEN = "value-three"', ".toml")


def _insert_usage(app, rows):
    with app.state.database.connect() as connection:
        connection.executemany(
            """INSERT INTO usage_events
            (id, provider, session_id, model, occurred_at, input_tokens, output_tokens,
             cache_read_tokens, cache_write_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows,
        )


def test_five_hour_window_starts_at_first_message_after_the_previous_window(tmp_path: Path):
    from datetime import timedelta

    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    now = datetime.now(timezone.utc)
    stamp = lambda hours: (now - timedelta(hours=hours)).isoformat()  # noqa: E731
    with TestClient(app) as client:
        _insert_usage(app, [
            ("old", "claude", "s1", "claude-opus-5-5", stamp(9), 100, 0, 0, 0),   # earlier window, expired
            ("first", "claude", "s2", "claude-opus-5-5", stamp(2), 10, 0, 0, 0),  # opens the current window
            ("later", "claude", "s2", "claude-opus-5-5", stamp(1), 5, 0, 0, 0),
        ])
        window = client.get("/api/overview").json()["windows"][0]
        assert (window["active"], window["tokens"], window["sessions"]) == (True, 15, 1)
        resets = datetime.fromisoformat(window["resets_at"])
        assert abs((resets - (now + timedelta(hours=3))).total_seconds()) < 5


def test_overview_estimates_cost_from_the_price_table_and_lists_unpriced_models(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    now = datetime.now(timezone.utc).isoformat()
    with TestClient(app) as client:
        _insert_usage(app, [
            ("priced", "claude", "s1", "claude-opus-5-5", now, 1_000_000, 1_000_000, 1_000_000, 1_000_000),
            ("unpriced", "opencode", "s2", "mystery-model", now, 500, 500, 0, 0),
        ])
        overview = client.get("/api/overview").json()
        priced = next(item for item in overview["models"] if item["model"] == "claude-opus-5-5")
        # input 4 + output 20 + cache read 0.20 + cache write 5, per million tokens
        assert priced["estimated_cost_usd"] == 29.2
        assert overview["totals"]["estimated_cost_usd"] == 29.2
        assert overview["totals"]["cost_usd"] == 0
        assert overview["pricing"]["unpriced_models"] == ["mystery-model"]


def _insert_trace(app, rows):
    with app.state.database.connect() as connection:
        connection.executemany(
            """INSERT INTO trace_events(id, provider, session_id, occurred_at, kind, role, name, content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", rows,
        )


def test_search_finds_words_by_prefix_and_ignores_query_syntax(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    with TestClient(app) as client:
        _insert_trace(app, [
            ("a", "claude", "s1", "2026-08-31T00:00:00Z", "message", "user", None, "Fix the flaky scanner migration"),
            ("b", "codex", "s2", "2026-08-31T00:00:01Z", "message", "assistant", None, "Unrelated refactor notes"),
        ])
        found = client.get("/api/search", params={"q": "scan migr"}).json()
        assert found["mode"] == "fts"
        assert [item["id"] for item in found["results"]] == ["a"]
        assert "scanner" in found["results"][0]["snippet"]
        assert client.get("/api/search", params={"q": 'refactor" *'}).json()["results"][0]["id"] == "b"
        assert client.get("/api/search", params={"q": "scanner", "provider": "codex"}).json()["results"] == []
        # Edits and deletes keep the index in step.
        with app.state.database.connect() as connection:
            connection.execute("UPDATE trace_events SET content = 'rewritten' WHERE id = 'a'")
            connection.execute("DELETE FROM trace_events WHERE id = 'b'")
        assert client.get("/api/search", params={"q": "scanner"}).json()["results"] == []
        assert client.get("/api/search", params={"q": "refactor"}).json()["results"] == []
        assert client.get("/api/search", params={"q": "rewritten"}).json()["results"][0]["id"] == "a"


def test_session_and_usage_exports(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    now = datetime.now(timezone.utc).isoformat()
    with TestClient(app) as client:
        _insert_trace(app, [
            ("a", "claude", "s1", "2026-08-31T00:00:00Z", "message", "user", None, "Hello"),
            ("b", "claude", "s1", "2026-08-31T00:00:01Z", "tool_call", "assistant", "Bash", "echo ```hi```"),
        ])
        _insert_usage(app, [("u", "claude", "s1", "claude-opus-5-5", now, 1_000_000, 0, 0, 0)])
        markdown = client.get("/api/providers/claude/sessions/s1/export")
        assert markdown.headers["content-type"].startswith("text/markdown")
        assert "## User" in markdown.text and "## Tool call: Bash" in markdown.text and "````" in markdown.text
        exported = client.get("/api/providers/claude/sessions/s1/export", params={"format": "json"}).json()
        assert [event["content"] for event in exported["events"]] == ["Hello", "echo ```hi```"]
        assert client.get("/api/providers/claude/sessions/missing/export").status_code == 404
        rows = client.get("/api/export/usage.csv").text.strip().splitlines()
        assert rows[0].startswith("day,provider,model")
        assert rows[1].endswith(",0,4.0")


class TraceAdapter(ProviderAdapter):
    id = "claude"
    name = "Claude Code"

    def __init__(self, source: Path, events: list[dict]):
        self.source, self.events = source, events

    def log_roots(self): return [self.source]
    def discover(self): return [self.source]
    def parse(self, path): return []
    def scan_source(self, path, state): return [], self.events, {"seen": True}


def _trace(event_id: str, occurred_at: str) -> dict:
    return {
        "id": event_id, "provider": "claude", "session_id": "s1", "project_path": None, "model": None,
        "occurred_at": occurred_at, "kind": "message", "role": "user", "name": None, "content": event_id,
        "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "metadata": {},
    }


def test_retention_prunes_old_transcript_text_but_keeps_usage(tmp_path: Path):
    from datetime import timedelta

    source = tmp_path / "session.jsonl"
    source.write_text("{}")
    now = datetime.now(timezone.utc)
    events = [_trace("old", (now - timedelta(days=40)).isoformat()), _trace("new", now.isoformat())]
    app = create_app(
        Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[TraceAdapter(source, events)]
    )
    with TestClient(app) as client:
        _insert_usage(app, [("u", "claude", "s1", "m", (now - timedelta(days=40)).isoformat(), 7, 0, 0, 0)])
        _insert_trace(app, [("stale", "claude", "s1", (now - timedelta(days=50)).isoformat(), "message", "user", None, "x")])
        assert client.patch("/api/settings", json={"trace_retention_days": 30}).json()["trace_retention_days"] == 30
        source.write_text("{}{}")  # changed size forces a rescan
        client.post("/api/scan")
        with app.state.database.connect() as connection:
            ids = {row["id"] for row in connection.execute("SELECT id FROM trace_events")}
            usage = connection.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
            state = connection.execute("SELECT state FROM scanned_files").fetchone()["state"]
        assert ids == {"new"}
        assert usage == 1
        assert state == '{"seen": true}'
        assert client.patch("/api/settings", json={"trace_retention_days": -1}).status_code == 422


def test_polling_endpoints_reuse_a_recent_scan(tmp_path: Path):
    calls = []

    class CountingAdapter(EmptyClaudeAdapter):
        def discover(self):
            calls.append(1)
            return []

    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[CountingAdapter()])
    with TestClient(app) as client:
        while not client.get("/api/health").json()["initial_scan_complete"]:
            pass  # let the background loop's first scan finish so it cannot race the count
        client.post("/api/scan")
        before = len(calls)
        for _ in range(5):
            client.get("/api/providers/claude/sessions")
        assert len(calls) == before
        client.post("/api/scan")
        assert len(calls) == before + 1


def test_session_cost_is_estimated_per_model_and_shows_the_dominant_model(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[EmptyClaudeAdapter()])
    now = datetime.now(timezone.utc).isoformat()
    with TestClient(app) as client:
        _insert_usage(app, [
            ("big", "claude", "s1", "claude-opus-5-5", now, 1_000_000, 0, 0, 0),   # $4.00
            ("small", "claude", "s1", "claude-sonnet-5-5", now, 500_000, 0, 0, 0),  # $1.00
        ])
        session = client.get("/api/providers/claude/sessions").json()[0]
        assert session["model"] == "claude-opus-5-5"
        assert session["estimated_cost_usd"] == 5.0
