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


def create_app(settings: Settings | None = None, job_catalog: JobCatalog | None = None) -> FastAPI:
    settings = settings or get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.job_catalog = job_catalog or build_job_catalog(settings)

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
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(jobs_router, prefix="/api")
    return application


app = create_app()
