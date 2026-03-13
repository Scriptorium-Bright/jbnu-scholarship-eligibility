from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services.health import build_ready_payload

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.get("/ready")
def ready() -> JSONResponse:
    payload = build_ready_payload()
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)
