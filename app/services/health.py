from typing import Dict

from app.db.session import database_healthcheck


def build_ready_payload() -> Dict[str, object]:
    """
    데이터베이스 등 핵심 인프라 연결 상태를 검사하여 Readiness 검증 결과를 생성합니다.
    모든 검사가 정상이면 'ok', 문제 발생 시 'degraded' 상태를 식별케 합니다.
    """
    database_check = database_healthcheck()
    overall_status = "ok" if database_check["status"] == "ok" else "degraded"
    return {
        "status": overall_status,
        "checks": {
            "database": database_check,
        },
    }
