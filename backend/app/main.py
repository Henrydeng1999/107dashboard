from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.projects import router as projects_router
from app.api.routes.product import router as product_router
from app.core.config import Settings, get_settings
from app.services.demo_fallback import DemoFallbackJobCatalog
from app.services.job_catalog import JobCatalog, build_job_catalog
from app.schemas.system import RuntimeCapabilities, RuntimeInfo
from app.services.test_projects import TestProjectCatalog
from app.repositories.product import ProductRepository
from app.services.product import ProductService


def _runtime_info(
    settings: Settings, job_catalog: JobCatalog | DemoFallbackJobCatalog
) -> RuntimeInfo:
    fallback_status = (
        job_catalog.status() if isinstance(job_catalog, DemoFallbackJobCatalog) else None
    )
    fallback_active = fallback_status is not None and fallback_status.active
    native_submission_enabled = (
        settings.slurm_data_source == "native"
        and settings.native_submission_enabled
        and not fallback_active
    )
    native_write_enabled = native_submission_enabled or (
        settings.slurm_data_source == "native"
        and not fallback_active
        and (settings.native_cancel_enabled or settings.native_clone_enabled)
    )
    native_read_only = settings.slurm_data_source == "native" and not native_write_enabled
    return RuntimeInfo(
        data_source=settings.slurm_data_source,
        serving_source=(
            "fixture_fallback"
            if fallback_active
            else "native"
            if settings.slurm_data_source == "native"
            else "fixture"
        ),
        read_only=native_read_only,
        degraded=fallback_active,
        demo_fallback_enabled=isinstance(job_catalog, DemoFallbackJobCatalog),
        fallback_reason=fallback_status.reason if fallback_status is not None else None,
        capabilities=RuntimeCapabilities(
            submit=(settings.slurm_data_source == "fixture" or native_submission_enabled),
            cancel=(
                settings.slurm_data_source == "fixture"
                or (
                    settings.slurm_data_source == "native"
                    and settings.native_cancel_enabled
                    and not fallback_active
                )
            ),
            clone=(
                settings.slurm_data_source == "fixture"
                or (
                    settings.slurm_data_source == "native"
                    and settings.native_clone_enabled
                    and not fallback_active
                )
            ),
            logs=(
                settings.slurm_data_source == "fixture"
                or fallback_active
                or (
                    settings.slurm_data_source == "native" and settings.native_logs_enabled
                )
            ),
        ),
    )


def create_app(
    settings: Settings | None = None,
    job_catalog: JobCatalog | DemoFallbackJobCatalog | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.job_catalog = job_catalog or build_job_catalog(settings)
    application.state.test_project_catalog = (
        TestProjectCatalog(settings.test_project_directory)
        if settings.test_project_directory is not None
        else None
    )
    application.state.runtime_info_provider = lambda: _runtime_info(
        settings, application.state.job_catalog
    )
    product_repository = ProductRepository(settings.database_url)
    product_repository.initialize()
    application.state.product_service = ProductService(
        owner=settings.dashboard_owner,
        repository=product_repository,
        secret_directory=settings.ai_secret_directory,
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
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(jobs_router, prefix="/api")
    application.include_router(projects_router, prefix="/api")
    application.include_router(product_router, prefix="/api")
    if settings.serve_frontend:
        frontend_index = settings.frontend_dist_directory / "index.html"
        if not frontend_index.is_file():
            raise ValueError("SERVE_FRONTEND requires a built frontend index.html")
        application.mount(
            "/",
            StaticFiles(directory=settings.frontend_dist_directory, html=True),
            name="frontend",
        )
    return application


app = create_app()
