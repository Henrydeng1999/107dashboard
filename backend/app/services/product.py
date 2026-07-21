from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request

from app.repositories.product import ProductRepository
from app.schemas.jobs import Job, JobState, JobUsageResponse
from app.schemas.product import (
    AiCallRecord,
    AiChatResponse,
    AiProvider,
    DiagnosticReport,
    EvaluationJob,
    EvaluationProject,
    PromptTemplate,
    ProviderTestResult,
    ReportEvidence,
    ReportFinding,
)
from app.services.job_catalog import JobCatalog, JobCatalogUnavailable, JobNotFound


class ProductNotFound(RuntimeError):
    pass


class AiProviderNotConfigured(RuntimeError):
    pass


class AiProviderUnavailable(RuntimeError):
    pass


PROVIDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _usage_or_none(catalog: JobCatalog, job_id: str) -> JobUsageResponse | None:
    try:
        return catalog.get_job_usage(job_id)
    except (JobCatalogUnavailable, JobNotFound):
        return None


def build_report(catalog: JobCatalog, job: Job) -> DiagnosticReport:
    usage = _usage_or_none(catalog, job.id)
    scores = {
        JobState.COMPLETED: 92,
        JobState.RUNNING: 75,
        JobState.PENDING: 65,
        JobState.CANCELLED: 50,
        JobState.FAILED: 35,
        JobState.TIMEOUT: 25,
        JobState.UNKNOWN: 45,
    }
    score = scores[job.state]
    findings: list[ReportFinding] = []
    if job.state == JobState.COMPLETED and job.exit_code in {None, "0:0", "0"}:
        summary = "作业正常完成；资源效率需要结合可用统计继续判断。"
    elif job.state in {JobState.FAILED, JobState.TIMEOUT}:
        summary = "作业未正常完成；应优先复核退出码、调度原因和 stderr。"
        findings.append(
            ReportFinding(
                severity="critical",
                title="作业异常终止",
                explanation=f"Slurm 状态为 {job.state.value}，退出码为 {job.exit_code or '未提供'}。",
                recommendation="查看 stderr 和调度原因，修正后再提交。",
            )
        )
    elif job.state == JobState.PENDING:
        summary = "作业仍在排队，当前不能判断程序执行结果。"
        findings.append(
            ReportFinding(
                severity="info",
                title="等待调度",
                explanation=job.reason or "Slurm 尚未分配节点。",
                recommendation="等待调度或检查分区资源情况。",
            )
        )
    else:
        summary = f"作业当前状态为 {job.state.value}。"
    if usage and usage.max_rss_kb is not None and usage.requested.memory_mb:
        ratio = usage.max_rss_kb / 1024 / usage.requested.memory_mb
        if ratio < 0.4:
            score = max(0, score - 5)
            findings.append(
                ReportFinding(
                    severity="warning",
                    title="内存申请偏高",
                    explanation=f"峰值内存约占申请值的 {ratio:.0%}。",
                    recommendation="在保留余量的前提下适当降低内存申请。",
                )
            )
    if not findings:
        findings.append(
            ReportFinding(
                severity="info",
                title="未发现明确异常",
                explanation="现有结构化证据没有触发异常规则。",
                recommendation="结合业务指标确认结果质量。",
            )
        )
    evidence = [
        ReportEvidence(key="state", label="Slurm 状态", value=job.state.value, source="slurm"),
        ReportEvidence(
            key="exit_code", label="退出码", value=job.exit_code or "未提供", source="slurm"
        ),
        ReportEvidence(
            key="reason", label="调度原因", value=job.reason or "未提供", source="slurm"
        ),
        ReportEvidence(
            key="requested",
            label="申请资源",
            value=f"CPU {job.resources.cpus or '—'} / GPU {job.resources.gpus if job.resources.gpus is not None else '—'} / 内存 {job.resources.memory_mb or '—'} MiB",
            source="metadata",
        ),
    ]
    if usage:
        evidence.extend(
            [
                ReportEvidence(
                    key="elapsed",
                    label="运行秒数",
                    value=str(usage.elapsed_seconds)
                    if usage.elapsed_seconds is not None
                    else "未提供",
                    source="usage",
                ),
                ReportEvidence(
                    key="max_rss",
                    label="峰值内存",
                    value=f"{usage.max_rss_kb} KiB" if usage.max_rss_kb is not None else "未提供",
                    source="usage",
                ),
                ReportEvidence(
                    key="total_cpu",
                    label="累计 CPU 秒",
                    value=str(usage.total_cpu_seconds)
                    if usage.total_cpu_seconds is not None
                    else "未提供",
                    source="usage",
                ),
            ]
        )
    return DiagnosticReport(
        job_id=job.id,
        slurm_job_id=job.slurm_job_id,
        job_name=job.name,
        state=job.state.value,
        health_score=score,
        summary=summary,
        evidence=evidence,
        findings=findings,
        generated_at=datetime.now(UTC),
    )


class ProductService:
    def __init__(self, owner: str, repository: ProductRepository, secret_directory: Path) -> None:
        self.owner = owner
        self.repository = repository
        self.secret_directory = secret_directory

    def report(self, catalog: JobCatalog, job_id: str) -> DiagnosticReport:
        job = catalog.get_job(job_id)
        if job is None:
            raise ProductNotFound("job not found")
        return build_report(catalog, job)

    def reports(self, catalog: JobCatalog) -> list[DiagnosticReport]:
        jobs = catalog.list_jobs(state=None, page=1, page_size=100).items
        return [build_report(catalog, job) for job in jobs]

    def create_project(
        self, catalog: JobCatalog, name: str, description: str, job_ids: list[str]
    ) -> EvaluationProject:
        for job_id in job_ids:
            if catalog.get_job(job_id) is None:
                raise ProductNotFound("job not found")
        record = self.repository.create_project(self.owner, name, description, job_ids)
        return self._evaluate(catalog, record)

    def projects(self, catalog: JobCatalog) -> list[EvaluationProject]:
        return [self._evaluate(catalog, item) for item in self.repository.list_projects(self.owner)]

    def project(self, catalog: JobCatalog, project_id: str) -> EvaluationProject:
        record = self.repository.get_project(self.owner, project_id)
        if record is None:
            raise ProductNotFound("project not found")
        return self._evaluate(catalog, record)

    def _evaluate(self, catalog: JobCatalog, record: dict) -> EvaluationProject:
        jobs: list[EvaluationJob] = []
        recommendations: list[str] = []
        evidence_fields = 0
        for job_id in record["job_ids"]:
            job = catalog.get_job(job_id)
            if job is None:
                continue
            report = build_report(catalog, job)
            usage = _usage_or_none(catalog, job.id)
            if usage and usage.elapsed_seconds is not None:
                evidence_fields += 1
            if usage and usage.max_rss_kb is not None:
                evidence_fields += 1
            jobs.append(
                EvaluationJob(
                    job_id=job.id,
                    slurm_job_id=job.slurm_job_id,
                    name=job.name,
                    state=job.state.value,
                    health_score=report.health_score,
                    elapsed_seconds=usage.elapsed_seconds if usage else None,
                    max_rss_kb=usage.max_rss_kb if usage else None,
                )
            )
        score = round(sum(job.health_score for job in jobs) / len(jobs)) if jobs else 0
        completed = sum(job.state == "COMPLETED" for job in jobs)
        if not jobs:
            recommendations.append("关联至少一个可见作业后再生成评价。")
        elif completed < len(jobs):
            recommendations.append("部分实验未正常完成，应先处理异常作业。")
        else:
            recommendations.append("所有关联作业均完成，可继续比较业务指标与复现结果。")
        coverage = round(evidence_fields / (len(jobs) * 2) * 100) if jobs else 0
        grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"
        return EvaluationProject(
            **record,
            jobs=jobs,
            score=score,
            grade=grade,
            summary=f"项目包含 {len(jobs)} 个可见作业，其中 {completed} 个正常完成。",
            recommendations=recommendations,
            evidence_coverage_percent=coverage,
        )

    def providers(self) -> list[AiProvider]:
        return [self._provider(item) for item in self.repository.list_providers(self.owner)]

    def upsert_provider(
        self, provider_id: str, name: str, base_url: str, model: str, api_key: str | None
    ) -> AiProvider:
        key_hint = None
        if api_key is not None:
            self.secret_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.secret_directory, 0o700)
            path = self._secret_path(provider_id)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.secret_directory, prefix=f".{provider_id}-", suffix=".key"
            )
            try:
                os.chmod(temporary_name, 0o600)
                os.write(descriptor, api_key.encode("utf-8"))
            finally:
                os.close(descriptor)
            try:
                os.replace(temporary_name, path)
            except OSError:
                Path(temporary_name).unlink(missing_ok=True)
                raise
            key_hint = f"••••{api_key[-4:]}"
        record = self.repository.upsert_provider(
            self.owner, provider_id, name, base_url.rstrip("/"), model, key_hint
        )
        return self._provider(record)

    def chat(
        self, catalog: JobCatalog, provider_id: str, message: str, job_ids: list[str]
    ) -> AiChatResponse:
        provider = self.repository.get_provider(self.owner, provider_id)
        if provider is None or not self._secret_exists(provider_id):
            raise AiProviderNotConfigured("provider is not configured")
        context = []
        for job_id in job_ids:
            context.append(self.report(catalog, job_id).model_dump(mode="json"))
        prompt = f"用户问题：{message}\n结构化作业证据：{json.dumps(context, ensure_ascii=False)}"
        try:
            answer = self._call_provider(provider, prompt)
            call = self.repository.add_call(
                self.owner, provider_id, provider["model"], "SUCCEEDED", message[:200], answer[:200]
            )
        except AiProviderUnavailable:
            self.repository.add_call(
                self.owner, provider_id, provider["model"], "FAILED", message[:200], None
            )
            raise
        return AiChatResponse(
            id=call["id"],
            provider_id=provider_id,
            model=provider["model"],
            answer=answer,
            evidence_job_ids=job_ids,
            created_at=call["created_at"],
        )

    def calls(self) -> list[AiCallRecord]:
        return [AiCallRecord(**item) for item in self.repository.list_calls(self.owner)]

    def test_provider(self, provider_id: str) -> ProviderTestResult:
        provider = self.repository.get_provider(self.owner, provider_id)
        if provider is None:
            raise AiProviderNotConfigured("provider not found")
        configured = self._secret_exists(provider_id)
        if not configured:
            return ProviderTestResult(
                provider_id=provider_id,
                configured=False,
                reachable=False,
                authenticated=False,
                model=None,
                latency_ms=None,
                error="API key not configured",
                key_hint=provider.get("key_hint"),
            )
        return self._test_connection(provider)

    def _test_connection(self, provider: dict) -> ProviderTestResult:
        payload = json.dumps(
            {
                "model": provider["model"],
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
                "temperature": 0.0,
            }
        ).encode()
        request = urllib.request.Request(
            f"{provider['base_url']}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._read_secret(provider['id'])}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        start = datetime.now(UTC)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read(200_000))
            latency = int((datetime.now(UTC) - start).total_seconds() * 1000)
            str(result["choices"][0]["message"]["content"])
            return ProviderTestResult(
                provider_id=provider["id"],
                configured=True,
                reachable=True,
                authenticated=True,
                model=provider["model"],
                latency_ms=latency,
                error=None,
                key_hint=provider.get("key_hint"),
            )
        except urllib.error.HTTPError as exc:
            latency = int((datetime.now(UTC) - start).total_seconds() * 1000)
            auth_failed = exc.code == 401 or exc.code == 403
            return ProviderTestResult(
                provider_id=provider["id"],
                configured=True,
                reachable=True,
                authenticated=not auth_failed,
                model=provider["model"],
                latency_ms=latency,
                error=f"HTTP {exc.code}: {exc.reason}",
                key_hint=provider.get("key_hint"),
            )
        except (OSError, urllib.error.URLError) as exc:
            latency = int((datetime.now(UTC) - start).total_seconds() * 1000)
            return ProviderTestResult(
                provider_id=provider["id"],
                configured=True,
                reachable=False,
                authenticated=False,
                model=None,
                latency_ms=latency,
                error=f"Connection failed: {exc.reason if isinstance(exc, urllib.error.URLError) else str(exc)}",
                key_hint=provider.get("key_hint"),
            )
        except (ValueError, KeyError, IndexError) as exc:
            return ProviderTestResult(
                provider_id=provider["id"],
                configured=True,
                reachable=True,
                authenticated=True,
                model=None,
                latency_ms=None,
                error=f"Unexpected response format: {exc}",
                key_hint=provider.get("key_hint"),
            )

    @staticmethod
    def templates() -> list[PromptTemplate]:
        return [
            PromptTemplate(
                id="job-diagnosis",
                name="作业诊断解释",
                description="解释结构化报告，不修改平台事实。",
                system_prompt="仅根据提供的 Slurm 证据回答，区分事实、推断和建议。",
            ),
            PromptTemplate(
                id="project-review",
                name="项目结果评价",
                description="比较已关联作业的结果与资源证据。",
                system_prompt="基于项目结构化指标评价，明确证据缺口。",
            ),
        ]

    def _provider(self, record: dict) -> AiProvider:
        return AiProvider(
            id=record["id"],
            name=record["name"],
            base_url=record["base_url"],
            model=record["model"],
            configured=self._secret_exists(record["id"]),
            key_hint=record["key_hint"],
            updated_at=record["updated_at"],
        )

    def _secret_path(self, provider_id: str) -> Path:
        if PROVIDER_ID_PATTERN.fullmatch(provider_id) is None:
            raise ValueError("invalid AI provider id")
        return self.secret_directory / f"{provider_id}.key"

    def _read_secret(self, provider_id: str) -> str:
        path = self._secret_path(provider_id)
        if path.is_symlink() or not path.is_file():
            raise AiProviderNotConfigured("provider secret is not a regular file")
        return path.read_text(encoding="utf-8")

    def _secret_exists(self, provider_id: str) -> bool:
        path = self._secret_path(provider_id)
        return not path.is_symlink() and path.is_file()

    def _call_provider(self, provider: dict, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": provider["model"],
                "messages": [
                    {
                        "role": "system",
                        "content": "你是只读的 Slurm 作业分析助手，不得声称执行了作业控制。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            }
        ).encode()
        request = urllib.request.Request(
            f"{provider['base_url']}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._read_secret(provider['id'])}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read(2_000_000))
            return str(result["choices"][0]["message"]["content"])
        except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError) as exc:
            raise AiProviderUnavailable("AI provider request failed") from exc
