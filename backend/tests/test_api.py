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
        assert len(overview["windows"]) == 2


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
    encoded_project = str(project).replace("/", "-")
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
