from pathlib import Path

import pytest

from app.repositories.submission import SubmissionRepository
from app.schemas.jobs import JobSubmitRequest
from app.services.native_submission import (
    ExplicitSubmissionAuthorization,
    NativeActiveJobLimitError,
    NativeIdempotencyConflictError,
    NativeIdempotencyRequiredError,
    NativeSubmissionService,
)
from app.slurm.submission import SubmissionPlan


def request() -> JobSubmitRequest:
    return JobSubmitRequest.model_validate(
        {
            "name": "preflight-job",
            "command": "python3 --version",
            "partition": "Students",
            "account": "stu",
            "qos": "qos_stu_default",
            "resources": {
                "cpus": 1,
                "memory_mb": 512,
                "gpus": 0,
                "time_limit_minutes": 1,
            },
        }
    )


class FakeSubmitter:
    def __init__(self, *, result: str = "21482") -> None:
        self.result = result
        self.calls = 0

    def submit(self, plan: SubmissionPlan) -> str:
        assert plan.script_path.exists()
        self.calls += 1
        return self.result


def build_service(tmp_path: Path) -> tuple[NativeSubmissionService, SubmissionRepository, FakeSubmitter]:
    repository = SubmissionRepository(f"sqlite:///{tmp_path / 'metadata.sqlite3'}")
    repository.initialize()
    submitter = FakeSubmitter()
    service = NativeSubmissionService(
        owner="pb24030760",
        workspace_root=tmp_path / "jobs",
        submitter=submitter,
        repository=repository,
    )
    return service, repository, submitter


def test_explicit_authorization_is_required_before_any_write(tmp_path: Path) -> None:
    service, repository, submitter = build_service(tmp_path)
    with pytest.raises(PermissionError):
        service.submit(request(), authorization=ExplicitSubmissionAuthorization())
    assert submitter.calls == 0
    assert repository.list_events(owner="pb24030760") == []
    assert not (tmp_path / "jobs").exists()


def test_authorized_fake_submission_persists_metadata_audit_and_receipt(tmp_path: Path) -> None:
    service, repository, submitter = build_service(tmp_path)
    metadata = service.submit(
        request(), authorization=ExplicitSubmissionAuthorization(confirmed=True)
    )
    assert submitter.calls == 1
    assert metadata.source == "native"
    assert metadata.owner == "pb24030760"
    assert metadata.slurm_job_id == "21482"
    assert Path(metadata.stdout_path or "").is_relative_to(tmp_path / "jobs")
    receipt = Path(metadata.stdout_path or "").parent / "slurm-job-id"
    assert receipt.read_text(encoding="ascii") == "21482\n"
    events = repository.list_events(owner="pb24030760")
    assert [(event.status, event.result_code) for event in events] == [
        ("PREPARED", "VALIDATED"),
        ("SUCCEEDED", "SBATCH_ACCEPTED"),
    ]
    assert all(event.owner == "pb24030760" for event in events)


def test_submit_failure_records_sanitized_event(tmp_path: Path) -> None:
    class FailingSubmitter:
        def submit(self, plan: SubmissionPlan) -> str:
            raise RuntimeError("secret stderr must not be persisted")

    repository = SubmissionRepository(f"sqlite:///{tmp_path / 'metadata.sqlite3'}")
    repository.initialize()
    service = NativeSubmissionService(
        owner="pb24030760",
        workspace_root=tmp_path / "jobs",
        submitter=FailingSubmitter(),
        repository=repository,
    )
    with pytest.raises(RuntimeError):
        service.submit(
            request(), authorization=ExplicitSubmissionAuthorization(confirmed=True)
        )
    events = repository.list_events(owner="pb24030760")
    assert events[-1].status == "FAILED"
    assert events[-1].result_code == "RUNTIMEERROR"
    assert "secret" not in repr(events)


def test_job_id_receipt_survives_metadata_commit_failure(tmp_path: Path) -> None:
    class FailingCommitRepository(SubmissionRepository):
        def record_success(
            self, metadata: object, audit: object, **kwargs: object
        ) -> object:
            del metadata, audit, kwargs
            raise RuntimeError("database unavailable")

    repository = FailingCommitRepository(f"sqlite:///{tmp_path / 'metadata.sqlite3'}")
    repository.initialize()
    service = NativeSubmissionService(
        owner="pb24030760",
        workspace_root=tmp_path / "jobs",
        submitter=FakeSubmitter(result="21483"),
        repository=repository,
    )
    with pytest.raises(RuntimeError):
        service.submit(
            request(), authorization=ExplicitSubmissionAuthorization(confirmed=True)
        )
    receipts = list((tmp_path / "jobs").glob("submission-*/slurm-job-id"))
    assert len(receipts) == 1
    assert receipts[0].read_text(encoding="ascii") == "21483\n"
    assert repository.list_events(owner="pb24030760")[-1].status == "FAILED"


@pytest.mark.parametrize("key", [None, "short", "contains spaces"])
def test_idempotent_submission_requires_valid_key(tmp_path: Path, key: str | None) -> None:
    service, repository, submitter = build_service(tmp_path)
    with pytest.raises(NativeIdempotencyRequiredError):
        service.submit_idempotent(
            request(),
            authorization=ExplicitSubmissionAuthorization(confirmed=True),
            idempotency_key=key,
            active_job_count=lambda: 0,
            max_active_jobs=1,
        )
    assert submitter.calls == 0
    assert repository.list_events(owner="pb24030760") == []


def test_active_limit_rejects_before_reservation_or_submit(tmp_path: Path) -> None:
    service, repository, submitter = build_service(tmp_path)
    with pytest.raises(NativeActiveJobLimitError):
        service.submit_idempotent(
            request(),
            authorization=ExplicitSubmissionAuthorization(confirmed=True),
            idempotency_key="request-active-limit-1",
            active_job_count=lambda: 1,
            max_active_jobs=1,
        )
    assert submitter.calls == 0
    assert repository.list_events(owner="pb24030760") == []


def test_successful_idempotent_replay_does_not_submit_twice(tmp_path: Path) -> None:
    service, repository, submitter = build_service(tmp_path)
    active_checks = 0

    def active_job_count() -> int:
        nonlocal active_checks
        active_checks += 1
        return 0

    first = service.submit_idempotent(
        request(),
        authorization=ExplicitSubmissionAuthorization(confirmed=True),
        idempotency_key="request-replay-safe-1",
        active_job_count=active_job_count,
        max_active_jobs=1,
    )
    replay = service.submit_idempotent(
        request(),
        authorization=ExplicitSubmissionAuthorization(confirmed=True),
        idempotency_key="request-replay-safe-1",
        active_job_count=active_job_count,
        max_active_jobs=1,
    )
    assert first == replay
    assert first.id == "slurm-21482"
    assert submitter.calls == 1
    assert active_checks == 1
    assert len(repository.list_events(owner="pb24030760")) == 2


def test_idempotency_key_cannot_be_reused_for_different_request(tmp_path: Path) -> None:
    service, _, submitter = build_service(tmp_path)
    service.submit_idempotent(
        request(),
        authorization=ExplicitSubmissionAuthorization(confirmed=True),
        idempotency_key="request-conflict-safe-1",
        active_job_count=lambda: 0,
        max_active_jobs=1,
    )
    changed = request().model_copy(update={"name": "different-job"})
    with pytest.raises(NativeIdempotencyConflictError):
        service.submit_idempotent(
            changed,
            authorization=ExplicitSubmissionAuthorization(confirmed=True),
            idempotency_key="request-conflict-safe-1",
            active_job_count=lambda: 0,
            max_active_jobs=1,
        )
    assert submitter.calls == 1
