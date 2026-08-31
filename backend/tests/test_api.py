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
        assert len(overview["windows"]) == 2


def test_settings_round_trip(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "test.db"), adapters=[])
    with TestClient(app) as client:
        response = client.patch("/api/settings", json={"scan_interval_seconds": 45})
        assert response.status_code == 200
        assert response.json()["scan_interval_seconds"] == 45
