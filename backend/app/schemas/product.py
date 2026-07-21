from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class ReportEvidence(BaseModel):
    key: str
    label: str
    value: str
    source: Literal["slurm", "usage", "metadata"]


class ReportFinding(BaseModel):
    severity: Literal["info", "warning", "critical"]
    title: str
    explanation: str
    recommendation: str


class DiagnosticReport(BaseModel):
    job_id: str
    slurm_job_id: str
    job_name: str
    state: str
    health_score: int = Field(ge=0, le=100)
    summary: str
    evidence: list[ReportEvidence]
    findings: list[ReportFinding]
    generated_at: datetime
    generator_version: str = "rules-v1"


class DiagnosticReportList(BaseModel):
    items: list[DiagnosticReport]


class EvaluationProjectCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff._ -]*$",
    )
    description: str = Field(default="", max_length=500)
    job_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("job_ids")
    @classmethod
    def unique_job_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("job_ids must be unique")
        return value


class EvaluationJob(BaseModel):
    job_id: str
    slurm_job_id: str
    name: str
    state: str
    health_score: int
    elapsed_seconds: float | None
    max_rss_kb: int | None


class EvaluationProject(BaseModel):
    id: str
    name: str
    description: str
    job_ids: list[str]
    jobs: list[EvaluationJob]
    score: int
    grade: str
    summary: str
    recommendations: list[str]
    evidence_coverage_percent: int
    created_at: datetime
    updated_at: datetime


class EvaluationProjectList(BaseModel):
    items: list[EvaluationProject]


class AiProviderUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    base_url: HttpUrl
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:/-]+$")
    api_key: str | None = Field(default=None, min_length=8, max_length=4096)

    @field_validator("base_url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("AI provider base_url must use HTTPS")
        return value


class AiProvider(BaseModel):
    id: str
    name: str
    base_url: str
    model: str
    configured: bool
    key_hint: str | None
    updated_at: datetime


class AiProviderList(BaseModel):
    items: list[AiProvider]


class AiChatRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=8000)
    job_ids: list[str] = Field(default_factory=list, max_length=20)


class AiChatResponse(BaseModel):
    id: str
    provider_id: str
    model: str
    answer: str
    evidence_job_ids: list[str]
    tools_used: list[str] = Field(default_factory=list)
    created_at: datetime


class AiCallRecord(BaseModel):
    id: str
    provider_id: str
    model: str
    status: Literal["SUCCEEDED", "FAILED"]
    prompt_preview: str
    response_preview: str | None
    created_at: datetime


class AiCallRecordList(BaseModel):
    items: list[AiCallRecord]


class ProviderTestResult(BaseModel):
    provider_id: str
    configured: bool
    reachable: bool
    authenticated: bool
    model: str | None
    latency_ms: int | None
    error: str | None
    key_hint: str | None


class PromptTemplate(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str


class PromptTemplateList(BaseModel):
    items: list[PromptTemplate]
