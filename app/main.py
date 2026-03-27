from fastapi import FastAPI

from app.api.router import api_router
from app.api.routers.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    """
    FastAPI 어플리케이션 객체를 생성하고 초기화합니다.
    설정, 로깅, 라우터 연결 등 전역 환경을 구성하여 반환합니다.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.include_router(health_router)
    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()
