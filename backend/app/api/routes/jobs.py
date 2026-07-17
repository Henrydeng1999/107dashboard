from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.schemas.jobs import ErrorResponse, Job, JobListResponse, JobState, JobSubmitRequest
from app.services.job_catalog import (
    JobCatalog,
    JobCatalogUnavailable,
    JobNotFound,
    JobOperationConflict,
    JobSubmissionUnavailable,
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


@router.post(
    "",
    response_model=Job,
    status_code=201,
    responses={
        422: ERROR_RESPONSES[422],
        503: {"model": ErrorResponse, "description": "Job submission unavailable"},
    },
)
def submit_job(
    submission: JobSubmitRequest,
    request: Request,
    catalog: CatalogDependency,
) -> Job | JSONResponse:
    try:
        return catalog.submit_job(submission)
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
) -> Job | JSONResponse:
    try:
        return catalog.cancel_job(job_id) if operation == "cancel" else catalog.clone_job(job_id)
    except JobNotFound:
        return _error_response(request, 404, "JOB_NOT_FOUND", "Job was not found")
    except JobOperationConflict:
        return _error_response(
            request,
            409,
            "JOB_OPERATION_CONFLICT",
            "Job cannot be operated on in its current state",
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
def cancel_job(job_id: str, request: Request, catalog: CatalogDependency) -> Job | JSONResponse:
    return _job_operation("cancel", job_id, request, catalog)


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
def clone_job(job_id: str, request: Request, catalog: CatalogDependency) -> Job | JSONResponse:
    return _job_operation("clone", job_id, request, catalog)
