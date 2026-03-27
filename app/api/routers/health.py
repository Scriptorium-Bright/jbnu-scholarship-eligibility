from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services.health import build_ready_payload

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """
    서버의 기본 구동 상태(Liveness)를 확인합니다.
    최소한의 서비스 정보와 상태 'ok'를 반환합니다.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.get("/ready")
def ready() -> JSONResponse:
    """
    서버가 실제 요청을 수락할 준비(Readiness)가 되었는지 검증합니다.
    내부 의존성 상태를 확인하여 적절한 HTTP 상태 코드를 반환합니다.
    """
    payload = build_ready_payload()
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)
