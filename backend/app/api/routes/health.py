from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.schemas.system import RuntimeInfo

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "dashboard-api", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/runtime", response_model=RuntimeInfo)
def runtime_info(request: Request) -> RuntimeInfo:
    return request.app.state.runtime_info
