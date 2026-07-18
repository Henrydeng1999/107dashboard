from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.core.config import Settings, get_settings
from app.services.job_catalog import JobCatalog, build_job_catalog
from app.schemas.system import RuntimeCapabilities, RuntimeInfo


def create_app(settings: Settings | None = None, job_catalog: JobCatalog | None = None) -> FastAPI:
    settings = settings or get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.job_catalog = job_catalog or build_job_catalog(settings)
    native_submission_enabled = (
        settings.slurm_data_source == "native" and settings.native_submission_enabled
    )
    native_write_enabled = native_submission_enabled or (
        settings.slurm_data_source == "native"
        and (settings.native_cancel_enabled or settings.native_clone_enabled)
    )
    native_read_only = settings.slurm_data_source == "native" and not native_write_enabled
    application.state.runtime_info = RuntimeInfo(
        data_source=settings.slurm_data_source,
        read_only=native_read_only,
        capabilities=RuntimeCapabilities(
            submit=(settings.slurm_data_source == "fixture" or native_submission_enabled),
            cancel=(
                settings.slurm_data_source == "fixture"
                or (settings.slurm_data_source == "native" and settings.native_cancel_enabled)
            ),
            clone=(
                settings.slurm_data_source == "fixture"
                or (settings.slurm_data_source == "native" and settings.native_clone_enabled)
            ),
            logs=(
                settings.slurm_data_source == "fixture"
                or (settings.slurm_data_source == "native" and settings.native_logs_enabled)
            ),
        ),
    )

    @application.middleware("http")
    async def assign_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request parameters are invalid",
                    "request_id": request.state.request_id,
                }
            },
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(jobs_router, prefix="/api")
    return application


app = create_app()
