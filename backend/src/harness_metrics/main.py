import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from harness_metrics.api.routes import router
from harness_metrics.config import Settings, settings
from harness_metrics.database import Database
from harness_metrics.providers import ProviderAdapter, provider_registry
from harness_metrics.services.analytics import AnalyticsService
from harness_metrics.services.scanner import UsageScanner


def create_app(app_settings: Settings = settings, adapters: list[ProviderAdapter] | None = None) -> FastAPI:
    database = Database(app_settings.db_path)
    providers = provider_registry() if adapters is None else adapters
    scanner = UsageScanner(database, providers)

    async def scan_loop() -> None:
        while True:
            await asyncio.to_thread(scanner.scan)
            interval = database.setting("scan_interval_seconds", app_settings.scan_interval_seconds)
            await asyncio.sleep(int(interval))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.initialize()
        await asyncio.to_thread(scanner.scan)
        task = asyncio.create_task(scan_loop())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="Hubble", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"], allow_headers=["*"],
    )
    app.state.settings = app_settings
    app.state.database = database
    app.state.providers = providers
    app.state.scanner = scanner
    app.state.analytics = AnalyticsService(database)
    app.include_router(router)
    return app


app = create_app()
