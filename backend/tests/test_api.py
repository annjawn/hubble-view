from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from harness_metrics.config import Settings
from harness_metrics.main import create_app


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
