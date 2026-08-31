from pathlib import Path

from platformdirs import user_data_dir
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Hubble"
    data_dir: Path = Path(user_data_dir("HarnessMetrics", "HarnessMetrics"))
    database_path: Path | None = None
    scan_interval_seconds: int = 30
    host: str = "127.0.0.1"
    port: int = 8765
    model_config = SettingsConfigDict(env_prefix="HARNESS_METRICS_")

    @property
    def db_path(self) -> Path:
        return self.database_path or self.data_dir / "metrics.db"


settings = Settings()
