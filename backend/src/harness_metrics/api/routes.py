from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter(prefix="/api")

# Session views poll every few seconds. A poll reuses a scan that finished
# within this window instead of walking every provider's files again.
LIVE_SCAN_MAX_AGE_SECONDS = 3.0


class SettingsUpdate(BaseModel):
    scan_interval_seconds: int | None = None
    launch_at_login: bool | None = None
    minimize_to_tray: bool | None = None
    trace_retention_days: int | None = None


@router.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "version": request.app.version,
        "initial_scan_complete": bool(getattr(request.app.state, "initial_scan_complete", True)),
    }


@router.get("/overview")
def overview(request: Request, days: int = Query(7, ge=1, le=365)):
    return request.app.state.analytics.overview(days)


@router.get("/providers")
def providers(request: Request):
    return [provider.status() for provider in request.app.state.providers]


@router.get("/providers/{provider}/sessions")
def provider_sessions(provider: str, request: Request):
    if provider not in {item.id for item in request.app.state.providers}:
        raise HTTPException(404, "Unknown provider")
    request.app.state.scanner.scan(max_age=LIVE_SCAN_MAX_AGE_SECONDS)
    return request.app.state.analytics.provider_sessions(provider)


@router.get("/providers/{provider}/artifacts")
def provider_artifacts(provider: str, request: Request):
    if provider not in {item.id for item in request.app.state.providers}:
        raise HTTPException(404, "Unknown provider")
    return request.app.state.artifacts.global_list(provider)


@router.get("/projects/artifacts")
def project_artifacts(request: Request, project_path: str = Query(...)):
    result = request.app.state.artifacts.project_list(project_path)
    if result is None:
        raise HTTPException(404, "Unknown project")
    return result


@router.get("/providers/{provider}/sessions/{session_id}/events")
def session_events(provider: str, session_id: str, request: Request, limit: int = Query(500, ge=1, le=2000)):
    request.app.state.scanner.scan(max_age=LIVE_SCAN_MAX_AGE_SECONDS)
    return request.app.state.analytics.session_events(provider, session_id, limit)


@router.get("/providers/{provider}/sessions/{session_id}/export")
def export_session(
    provider: str, session_id: str, request: Request,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
):
    exported = request.app.state.analytics.export_session(provider, session_id, format)
    if exported is None:
        raise HTTPException(404, "No stored transcript for this session")
    body, media_type = exported
    return Response(body, media_type=media_type)


@router.get("/export/usage.csv")
def export_usage(request: Request, days: int = Query(30, ge=1, le=3650)):
    return Response(request.app.state.analytics.export_usage_csv(days), media_type="text/csv")


@router.get("/search")
def search(
    request: Request, q: str = Query(..., min_length=2, max_length=200),
    provider: str | None = None, limit: int = Query(50, ge=1, le=200),
):
    return request.app.state.analytics.search(q, provider, limit)


@router.post("/scan")
def scan(request: Request):
    return {"imported": request.app.state.scanner.scan()}


@router.get("/settings")
def get_settings(request: Request):
    database = request.app.state.database
    return {
        "scan_interval_seconds": database.setting("scan_interval_seconds", 30),
        "launch_at_login": database.setting("launch_at_login", False),
        "minimize_to_tray": database.setting("minimize_to_tray", True),
        # 0 keeps transcript text forever; usage totals are never pruned.
        "trace_retention_days": database.setting("trace_retention_days", 0),
        "data_dir": str(request.app.state.settings.data_dir),
    }


@router.patch("/settings")
def update_settings(payload: SettingsUpdate, request: Request):
    values = payload.model_dump(exclude_none=True)
    if "scan_interval_seconds" in values and not 10 <= values["scan_interval_seconds"] <= 3600:
        raise HTTPException(422, "Scan interval must be between 10 and 3600 seconds")
    if "trace_retention_days" in values and not 0 <= values["trace_retention_days"] <= 3650:
        raise HTTPException(422, "Transcript retention must be between 0 and 3650 days")
    for key, value in values.items():
        request.app.state.database.set_setting(key, value)
    return get_settings(request)
