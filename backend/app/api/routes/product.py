from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
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
    PromptTemplate,
    PromptTemplateUpdate,
    ProviderModelList,
    ProviderModelTestRequest,
    ProviderTestResult,
)
from app.services.job_catalog import JobCatalog, JobCatalogUnavailable
from app.services.product import (
    AiProviderNotConfigured,
    AiProviderAuthenticationFailed,
    AiProviderRateLimited,
    AiProviderTimeout,
    AiProviderUnavailable,
    AiProviderModelConflict,
    ProductNotFound,
    ProductService,
)
from app.services.ai_tools import AiReadTools
from app.services.repositories import GitRepositoryNotFound

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
ModelId = Annotated[
    str,
    Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:/-]+$"),
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


@router.get("/ai/providers/{provider_id}/models", response_model=ProviderModelList)
def ai_provider_models(provider_id: ProviderId, request: Request, product: Service):
    try:
        return product.provider_models(provider_id)
    except AiProviderNotConfigured:
        return error(request, 404, "AI_PROVIDER_NOT_FOUND", "AI provider was not configured")
    except AiProviderUnavailable:
        return error(request, 503, "AI_PROVIDER_UNAVAILABLE", "AI provider models are unavailable")


@router.post("/ai/providers/{provider_id}/models/test", response_model=ProviderTestResult)
def test_ai_provider_model(
    provider_id: ProviderId,
    payload: ProviderModelTestRequest,
    request: Request,
    product: Service,
):
    try:
        return product.test_provider(provider_id, model=payload.model)
    except AiProviderNotConfigured:
        return error(request, 404, "AI_PROVIDER_NOT_FOUND", "AI provider was not found")


@router.post("/ai/providers/{provider_id}/models", response_model=AiProvider)
def add_ai_provider_model(
    provider_id: ProviderId, payload: ProviderModelTestRequest, request: Request, product: Service
):
    try:
        return product.add_provider_model(provider_id, payload.model)
    except AiProviderNotConfigured:
        return error(request, 404, "AI_PROVIDER_NOT_FOUND", "AI provider was not found")


@router.put("/ai/providers/{provider_id}/models/default", response_model=AiProvider)
def set_default_ai_provider_model(
    provider_id: ProviderId, payload: ProviderModelTestRequest, request: Request, product: Service
):
    try:
        return product.set_default_provider_model(provider_id, payload.model)
    except AiProviderNotConfigured:
        return error(request, 404, "AI_PROVIDER_MODEL_NOT_FOUND", "AI provider model was not found")


@router.delete("/ai/providers/{provider_id}/models", response_model=AiProvider)
def delete_ai_provider_model(
    provider_id: ProviderId, model: ModelId, request: Request, product: Service
):
    try:
        return product.delete_provider_model(provider_id, model)
    except AiProviderNotConfigured:
        return error(request, 404, "AI_PROVIDER_MODEL_NOT_FOUND", "AI provider model was not found")
    except AiProviderModelConflict:
        return error(request, 409, "AI_PROVIDER_MODEL_REQUIRED", "Provider must keep one model")


@router.get("/ai/templates", response_model=PromptTemplateList)
def ai_templates(product: Service):
    return PromptTemplateList(items=product.templates())


@router.put("/ai/templates/{template_id}", response_model=PromptTemplate)
def update_ai_template(
    template_id: ProviderId, payload: PromptTemplateUpdate, request: Request, product: Service
):
    try:
        return product.update_template(template_id, payload.system_prompt)
    except ProductNotFound:
        return error(request, 404, "AI_TEMPLATE_NOT_FOUND", "Prompt template was not found")


@router.delete("/ai/templates/{template_id}", response_model=PromptTemplate)
def reset_ai_template(template_id: ProviderId, request: Request, product: Service):
    try:
        return product.reset_template(template_id)
    except ProductNotFound:
        return error(request, 404, "AI_TEMPLATE_NOT_FOUND", "Prompt template was not found")


@router.get("/ai/calls", response_model=AiCallRecordList)
def ai_calls(product: Service):
    return AiCallRecordList(items=product.calls())


@router.post("/ai/chat", response_model=AiChatResponse)
def ai_chat(payload: AiChatRequest, request: Request, product: Service, jobs: Catalog):
    try:
        repository_context = []
        for repository_id in payload.repository_ids:
            detail = request.app.state.git_repository_browser.detail(repository_id)
            repository_context.append({
                "id": detail.repository.id,
                "name": detail.repository.name,
                "branch": detail.repository.branch,
                "head": detail.repository.head,
                "dirty": detail.repository.dirty,
                "changed_files": detail.repository.changed_files,
                "recent_commits": [
                    {
                        "hash": commit.hash,
                        "subject": commit.subject,
                        "authored_at": commit.authored_at.isoformat(),
                    }
                    for commit in detail.commits[:5]
                ],
            })
        tools = AiReadTools(
            runtime_info_provider=request.app.state.runtime_info_provider,
            jobs=jobs,
            product=product,
            repositories=request.app.state.git_repository_browser,
            test_projects=request.app.state.test_project_catalog,
            allowed_repository_ids=set(payload.repository_ids),
        )
        return product.chat(
            jobs,
            payload.provider_id,
            payload.model,
            payload.message,
            payload.job_ids,
            payload.repository_ids,
            repository_context,
            payload.template_id,
            tools,
        )
    except ProductNotFound:
        return error(request, 404, "JOB_NOT_FOUND", "One or more jobs were not found")
    except GitRepositoryNotFound:
        return error(request, 404, "REPOSITORY_NOT_FOUND", "Repository was not found")
    except AiProviderNotConfigured:
        return error(request, 409, "AI_PROVIDER_NOT_CONFIGURED", "AI provider is not configured")
    except AiProviderTimeout:
        return error(
            request,
            504,
            "AI_PROVIDER_TIMEOUT",
            "模型响应超时，请稍后重试或切换其他模型",
        )
    except AiProviderAuthenticationFailed:
        return error(request, 502, "AI_PROVIDER_AUTH_FAILED", "Provider 密钥已失效或无权调用该模型")
    except AiProviderRateLimited:
        return error(request, 429, "AI_PROVIDER_RATE_LIMITED", "模型当前请求过多，请稍后重试")
    except AiProviderUnavailable:
        return error(
            request, 502, "AI_PROVIDER_UNAVAILABLE", "模型服务暂时不可用，请稍后重试"
        )
