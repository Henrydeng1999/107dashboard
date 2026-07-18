from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from app.schemas.jobs import (
    ErrorResponse,
    Job,
    JobListResponse,
    JobLogResponse,
    JobLogStream,
    JobState,
    JobSubmitRequest,
    JobUsageResponse,
    UserJobSummary,
)
from app.services.job_catalog import (
    JobActiveLimitReached,
    JobCatalog,
    JobCatalogUnavailable,
    JobLogOffsetOutOfRange,
    JobLogsUnavailable,
    JobNotFound,
    JobIdempotencyConflict,
    JobIdempotencyRequired,
    JobOperationConflict,
    JobSubmissionUnavailable,
    JobSubmissionInvalid,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_catalog(request: Request) -> JobCatalog:
    return request.app.state.job_catalog


CatalogDependency = Annotated[JobCatalog, Depends(get_job_catalog)]


ERROR_RESPONSES = {
    422: {"model": ErrorResponse, "description": "Invalid request parameters"},
    503: {"model": ErrorResponse, "description": "Job data source unavailable"},
}


def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request.state.request_id,
            }
        },
    )


@router.get("", response_model=JobListResponse, responses=ERROR_RESPONSES)
def jobs(
    request: Request,
    catalog: CatalogDependency,
    state: JobState | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> JobListResponse | JSONResponse:
    try:
        return catalog.list_jobs(state=state, page=page, page_size=page_size)
    except JobCatalogUnavailable:
        return _error_response(
            request,
            503,
            "JOB_DATA_UNAVAILABLE",
            "Job data is temporarily unavailable",
        )


@router.get("/summary", response_model=UserJobSummary, responses=ERROR_RESPONSES)
def job_summary(request: Request, catalog: CatalogDependency) -> UserJobSummary | JSONResponse:
    try:
        return catalog.summarize_jobs()
    except JobCatalogUnavailable:
        return _error_response(
            request,
            503,
            "JOB_DATA_UNAVAILABLE",
            "Job data is temporarily unavailable",
        )


@router.get(
    "/{job_id}",
    response_model=Job,
    responses={
        **ERROR_RESPONSES,
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
def job_detail(job_id: str, request: Request, catalog: CatalogDependency) -> Job | JSONResponse:
    try:
        job = catalog.get_job(job_id)
    except JobCatalogUnavailable:
        return _error_response(
            request,
            503,
            "JOB_DATA_UNAVAILABLE",
            "Job data is temporarily unavailable",
        )
    if job is None:
        return _error_response(request, 404, "JOB_NOT_FOUND", "Job was not found")
    return job


@router.get(
    "/{job_id}/logs",
    response_model=JobLogResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        416: {"model": ErrorResponse, "description": "Log offset out of range"},
        503: {"model": ErrorResponse, "description": "Job logs unavailable"},
    },
)
def job_logs(
    job_id: str,
    request: Request,
    catalog: CatalogDependency,
    stream: JobLogStream = JobLogStream.STDOUT,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=16384, ge=1, le=65536),
) -> JobLogResponse | JSONResponse:
    try:
        return catalog.read_job_log(job_id, stream, offset, limit)
    except JobNotFound:
        return _error_response(request, 404, "JOB_NOT_FOUND", "Job was not found")
    except JobLogOffsetOutOfRange:
        return _error_response(
            request,
            416,
            "JOB_LOG_OFFSET_OUT_OF_RANGE",
            "Job log offset is beyond the available content",
        )
    except (JobCatalogUnavailable, JobLogsUnavailable):
        return _error_response(
            request,
            503,
            "JOB_LOGS_UNAVAILABLE",
            "Job logs are temporarily unavailable",
        )


@router.get(
    "/{job_id}/usage",
    response_model=JobUsageResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        503: {"model": ErrorResponse, "description": "Job usage unavailable"},
    },
)
def job_usage(
    job_id: str, request: Request, catalog: CatalogDependency
) -> JobUsageResponse | JSONResponse:
    try:
        return catalog.get_job_usage(job_id)
    except JobNotFound:
        return _error_response(request, 404, "JOB_NOT_FOUND", "Job was not found")
    except JobCatalogUnavailable:
        return _error_response(
            request,
            503,
            "JOB_USAGE_UNAVAILABLE",
            "Job usage is temporarily unavailable",
        )


@router.post(
    "",
    response_model=Job,
    status_code=201,
    responses={
        400: {"model": ErrorResponse, "description": "Idempotency key required"},
        409: {"model": ErrorResponse, "description": "Submission conflict"},
        422: ERROR_RESPONSES[422],
        503: {"model": ErrorResponse, "description": "Job submission unavailable"},
    },
)
def submit_job(
    submission: JobSubmitRequest,
    request: Request,
    catalog: CatalogDependency,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Job | JSONResponse:
    try:
        return catalog.submit_job(submission, idempotency_key=idempotency_key)
    except JobSubmissionInvalid:
        return _error_response(
            request,
            422,
            "INVALID_REQUEST",
            "Request parameters are invalid",
        )
    except JobIdempotencyRequired:
        return _error_response(
            request,
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "A valid Idempotency-Key header is required",
        )
    except JobIdempotencyConflict:
        return _error_response(
            request,
            409,
            "JOB_IDEMPOTENCY_CONFLICT",
            "Idempotency-Key conflicts with an earlier submission",
        )
    except JobActiveLimitReached:
        return _error_response(
            request,
            409,
            "JOB_ACTIVE_LIMIT_REACHED",
            "The active job limit has been reached",
        )
    except JobSubmissionUnavailable:
        return _error_response(
            request,
            503,
            "JOB_SUBMISSION_UNAVAILABLE",
            "Job submission is temporarily unavailable",
        )


def _job_operation(
    operation: str,
    job_id: str,
    request: Request,
    catalog: JobCatalog,
    idempotency_key: str | None,
) -> Job | JSONResponse:
    try:
        return (
            catalog.cancel_job(job_id, idempotency_key=idempotency_key)
            if operation == "cancel"
            else catalog.clone_job(job_id, idempotency_key=idempotency_key)
        )
    except JobNotFound:
        return _error_response(request, 404, "JOB_NOT_FOUND", "Job was not found")
    except JobOperationConflict:
        return _error_response(
            request,
            409,
            "JOB_OPERATION_CONFLICT",
            "Job cannot be operated on in its current state",
        )
    except JobIdempotencyRequired:
        return _error_response(
            request,
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "A valid Idempotency-Key header is required",
        )
    except JobIdempotencyConflict:
        return _error_response(
            request,
            409,
            "JOB_IDEMPOTENCY_CONFLICT",
            "Idempotency-Key conflicts with an earlier operation",
        )
    except JobSubmissionUnavailable:
        code = "JOB_CONTROL_UNAVAILABLE" if operation == "cancel" else "JOB_CLONE_UNAVAILABLE"
        return _error_response(
            request,
            503,
            code,
            "Job operation is temporarily unavailable",
        )


@router.post(
    "/{job_id}/cancel",
    response_model=Job,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        409: {"model": ErrorResponse, "description": "Job state conflict"},
        503: {"model": ErrorResponse, "description": "Job control unavailable"},
    },
)
def cancel_job(
    job_id: str,
    request: Request,
    catalog: CatalogDependency,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Job | JSONResponse:
    return _job_operation("cancel", job_id, request, catalog, idempotency_key)


@router.post(
    "/{job_id}/clone",
    response_model=Job,
    status_code=201,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        409: {"model": ErrorResponse, "description": "Job cannot be cloned"},
        503: {"model": ErrorResponse, "description": "Job cloning unavailable"},
    },
)
def clone_job(
    job_id: str,
    request: Request,
    catalog: CatalogDependency,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Job | JSONResponse:
    return _job_operation("clone", job_id, request, catalog, idempotency_key)
