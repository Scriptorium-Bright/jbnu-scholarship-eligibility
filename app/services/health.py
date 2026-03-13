from typing import Dict

from app.db.session import database_healthcheck


def build_ready_payload() -> Dict[str, object]:
    database_check = database_healthcheck()
    overall_status = "ok" if database_check["status"] == "ok" else "degraded"
    return {
        "status": overall_status,
        "checks": {
            "database": database_check,
        },
    }
