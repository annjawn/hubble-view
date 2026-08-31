from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api")


class SettingsUpdate(BaseModel):
    scan_interval_seconds: int | None = None
    launch_at_login: bool | None = None
    minimize_to_tray: bool | None = None


@router.get("/health")
def health(request: Request):
    return {"status": "ok", "version": request.app.version}


@router.get("/overview")
def overview(request: Request, days: int = Query(7, ge=1, le=365)):
    return request.app.state.analytics.overview(days)


@router.get("/providers")
def providers(request: Request):
    return [provider.status() for provider in request.app.state.providers]


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
        "data_dir": str(request.app.state.settings.data_dir),
    }


@router.patch("/settings")
def update_settings(payload: SettingsUpdate, request: Request):
    values = payload.model_dump(exclude_none=True)
    if "scan_interval_seconds" in values and not 10 <= values["scan_interval_seconds"] <= 3600:
        raise HTTPException(422, "Scan interval must be between 10 and 3600 seconds")
    for key, value in values.items():
        request.app.state.database.set_setting(key, value)
    return get_settings(request)

