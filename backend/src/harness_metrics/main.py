import asyncio
import logging
import secrets
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from harness_metrics.api.routes import router
from harness_metrics.config import Settings, settings
from harness_metrics.database import Database
from harness_metrics.providers import ProviderAdapter, provider_registry
from harness_metrics.services.analytics import AnalyticsService
from harness_metrics.services.artifacts import ArtifactService
from harness_metrics.services.scanner import UsageScanner

logger = logging.getLogger(__name__)


def create_app(app_settings: Settings = settings, adapters: list[ProviderAdapter] | None = None) -> FastAPI:
    database = Database(app_settings.db_path)
    providers = provider_registry() if adapters is None else adapters
    scanner = UsageScanner(database, providers)

    async def scan_loop() -> None:
        while True:
            interval = app_settings.scan_interval_seconds
            try:
                await asyncio.to_thread(database.backfill_search)
                await asyncio.to_thread(scanner.scan)
                interval = int(database.setting("scan_interval_seconds", interval))
            except Exception:  # noqa: BLE001 - a failed scan must not end background collection
                logger.exception("Background scan failed; retrying after the scan interval")
            finally:
                app.state.initial_scan_complete = True
            await asyncio.sleep(max(1, interval))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.initialize()
        # The first scan can take minutes on a large history. Run it in the
        # background so /api/health answers immediately; clients read
        # `initial_scan_complete` to know when the first import has finished.
        task = asyncio.create_task(scan_loop())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="Hubble", version="0.1.0", lifespan=lifespan)
    api_token = app_settings.api_token

    @app.middleware("http")
    async def require_api_token(request: Request, call_next):
        # When the desktop shell supplies a per-launch token, reject requests
        # that do not carry it. This keeps other local pages (including
        # `null`-origin documents and DNS-rebinding attempts) away from
        # transcript data. CORS preflights carry no credentials and pass.
        if api_token and request.method != "OPTIONS":
            supplied = request.headers.get("x-hubble-token", "")
            if not secrets.compare_digest(supplied.encode(), api_token.encode()):
                return JSONResponse({"detail": "Missing or invalid API token"}, status_code=401)
        return await call_next(request)

    # Added last so it wraps the token check and 401s still carry CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "null"],
        allow_methods=["*"], allow_headers=["*"],
    )
    app.state.settings = app_settings
    app.state.initial_scan_complete = False
    app.state.database = database
    app.state.providers = providers
    app.state.scanner = scanner
    app.state.analytics = AnalyticsService(database)
    app.state.artifacts = ArtifactService(database)
    app.include_router(router)
    return app


app = create_app()
