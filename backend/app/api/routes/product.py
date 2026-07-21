from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from app.schemas.product import (
    AiCallRecordList,
    AiChatRequest,
    AiChatResponse,
    AiProvider,
    AiProviderList,
    AiProviderUpsert,
    DiagnosticReport,
    DiagnosticReportList,
    EvaluationProject,
    EvaluationProjectCreate,
    EvaluationProjectList,
    PromptTemplateList,
    ProviderTestResult,
)
from app.services.job_catalog import JobCatalog, JobCatalogUnavailable
from app.services.product import (
    AiProviderNotConfigured,
    AiProviderUnavailable,
    ProductNotFound,
    ProductService,
)
from app.services.ai_tools import AiReadTools

router = APIRouter(tags=["product"])


def service(request: Request) -> ProductService:
    return request.app.state.product_service


def catalog(request: Request) -> JobCatalog:
    return request.app.state.job_catalog


Service = Annotated[ProductService, Depends(service)]
Catalog = Annotated[JobCatalog, Depends(catalog)]
ProviderId = Annotated[
    str,
    Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
]


def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "request_id": request.state.request_id}
        },
    )


@router.get("/reports", response_model=DiagnosticReportList)
def reports(request: Request, product: Service, jobs: Catalog):
    try:
        return DiagnosticReportList(items=product.reports(jobs))
    except JobCatalogUnavailable:
        return error(request, 503, "REPORTS_UNAVAILABLE", "Reports are temporarily unavailable")


@router.get("/reports/{job_id}", response_model=DiagnosticReport)
def report(job_id: str, request: Request, product: Service, jobs: Catalog):
    try:
        return product.report(jobs, job_id)
    except ProductNotFound:
        return error(request, 404, "JOB_NOT_FOUND", "Job was not found")


@router.get("/evaluation-projects", response_model=EvaluationProjectList)
def evaluation_projects(product: Service, jobs: Catalog):
    return EvaluationProjectList(items=product.projects(jobs))


@router.post("/evaluation-projects", response_model=EvaluationProject, status_code=201)
def create_evaluation_project(
    payload: EvaluationProjectCreate, request: Request, product: Service, jobs: Catalog
):
    try:
        return product.create_project(jobs, payload.name, payload.description, payload.job_ids)
    except ProductNotFound:
        return error(request, 404, "JOB_NOT_FOUND", "One or more jobs were not found")


@router.get("/evaluation-projects/{project_id}", response_model=EvaluationProject)
def evaluation_project(project_id: str, request: Request, product: Service, jobs: Catalog):
    try:
        return product.project(jobs, project_id)
    except ProductNotFound:
        return error(request, 404, "PROJECT_NOT_FOUND", "Project was not found")


@router.get("/ai/providers", response_model=AiProviderList)
def ai_providers(product: Service):
    return AiProviderList(items=product.providers())


@router.put("/ai/providers/{provider_id}", response_model=AiProvider)
def upsert_ai_provider(provider_id: ProviderId, payload: AiProviderUpsert, product: Service):
    return product.upsert_provider(
        provider_id, payload.name, str(payload.base_url), payload.model, payload.api_key
    )


@router.post("/ai/providers/{provider_id}/test", response_model=ProviderTestResult)
def test_ai_provider(provider_id: ProviderId, request: Request, product: Service):
    try:
        return product.test_provider(provider_id)
    except AiProviderNotConfigured:
        return error(request, 404, "AI_PROVIDER_NOT_FOUND", "AI provider was not found")


@router.get("/ai/templates", response_model=PromptTemplateList)
def ai_templates(product: Service):
    return PromptTemplateList(items=product.templates())


@router.get("/ai/calls", response_model=AiCallRecordList)
def ai_calls(product: Service):
    return AiCallRecordList(items=product.calls())


@router.post("/ai/chat", response_model=AiChatResponse)
def ai_chat(payload: AiChatRequest, request: Request, product: Service, jobs: Catalog):
    try:
        tools = AiReadTools(
            runtime_info_provider=request.app.state.runtime_info_provider,
            jobs=jobs,
            product=product,
            repositories=request.app.state.git_repository_browser,
            test_projects=request.app.state.test_project_catalog,
        )
        return product.chat(jobs, payload.provider_id, payload.message, payload.job_ids, tools)
    except ProductNotFound:
        return error(request, 404, "JOB_NOT_FOUND", "One or more jobs were not found")
    except AiProviderNotConfigured:
        return error(request, 409, "AI_PROVIDER_NOT_CONFIGURED", "AI provider is not configured")
    except AiProviderUnavailable:
        return error(
            request, 503, "AI_PROVIDER_UNAVAILABLE", "AI provider is temporarily unavailable"
        )
