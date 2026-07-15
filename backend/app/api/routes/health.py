from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "dashboard-api", "timestamp": datetime.now(UTC).isoformat()}
