import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.slurm.adapter import (
    SACCT_TARGET_MAX_JOB_IDS,
    FixtureSlurmAdapter,
    NativeSlurmAdapter,
)
from app.slurm.runner import (
    CommandResult,
    classify_slurm_failure,
    fingerprint_slurm_failure,
    SlurmCommandExecutionError,
    SlurmCommandFailed,
    SlurmCommandNotFound,
    SlurmCommandTimeout,
    SubprocessCommandRunner,
)

FIXTURE_DIRECTORY = Path(__file__).parents[3] / "fixtures" / "slurm"


class RecordingRunner:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout
        self.calls: list[list[str]] = []

    def run(self, arguments: list[str]) -> CommandResult:
        self.calls.append(list(arguments))
        return CommandResult(stdout=self.stdout, stderr="")


def test_fixture_adapter_uses_shared_parsers() -> None:
    adapter = FixtureSlurmAdapter(FIXTURE_DIRECTORY)

    assert adapter.list_queue("demo-user")[0].job_id == "900001"
    assert adapter.list_accounting("demo-user")[0].exit_code == "0:0"
    assert adapter.list_partitions()[0].name == "demo-students"
    assert adapter.list_queue("another-user") == []
    assert adapter.get_usage("899998")[1].max_rss_kb == 768 * 1024


def test_native_adapter_accepts_project_platform_username_styles() -> None:
    runner = RecordingRunner()
    adapter = NativeSlurmAdapter(runner)

    adapter.list_queue("pb24030760")

    assert runner.calls == [
        [
            "squeue",
            "--noheader",
            "--array",
            "--user=pb24030760",
            "--format=%i|%j|%T|%u|%P|%a|%q|%N|%r|%C|%m|%b|%l",
        ]
    ]


@pytest.mark.parametrize(
    "user",
    [
        "demo-user,other-user",
        "demo user",
        "\tdemo-user",
        "--all",
        "demo;whoami",
        "demo$(whoami)",
        "demo|whoami",
        "demo/user",
        "",
    ],
)
@pytest.mark.parametrize("method_name", ["list_queue", "list_accounting"])
def test_adapters_reject_non_single_or_unsafe_user_values(user: str, method_name: str) -> None:
    runner = RecordingRunner()
    adapter = NativeSlurmAdapter(runner)

    with pytest.raises(ValueError, match="one platform username"):
        getattr(adapter, method_name)(user)

    assert runner.calls == []


def test_fixture_adapter_applies_the_same_user_validation() -> None:
    adapter = FixtureSlurmAdapter(FIXTURE_DIRECTORY)

    with pytest.raises(ValueError, match="one platform username"):
        adapter.list_queue("demo-user,other-user")


def test_native_adapter_uses_structured_accounting_and_partition_formats() -> None:
    runner = RecordingRunner()
    adapter = NativeSlurmAdapter(runner)

    adapter.list_accounting("demo-user")
    adapter.list_partitions()

    assert runner.calls[0][0:7] == [
        "sacct",
        "--noheader",
        "--parsable2",
        "--allocations",
        "--user=demo-user",
        "--starttime=now-7days",
        "--endtime=now",
    ]
    assert runner.calls[0][7] == (
        "--format=JobIDRaw,JobName,State,User,Partition,Account,QOS,NodeList,ExitCode,"
        "ReqTRES,AllocTRES,Timelimit,Elapsed,Reason"
    )
    assert runner.calls[1] == [
        "sinfo",
        "--noheader",
        "--format=%P|%a|%t|%D|%C|%m|%G",
    ]


def test_native_adapter_batches_bounded_targeted_accounting_queries() -> None:
    runner = RecordingRunner()
    adapter = NativeSlurmAdapter(runner)
    job_ids = [str(job_id) for job_id in range(1, 52)]

    assert adapter.list_accounting_by_job_ids("demo-user", [*job_ids, "1"]) == []

    assert len(runner.calls) == 2
    assert runner.calls[0][0:5] == [
        "sacct",
        "--noheader",
        "--parsable2",
        "--allocations",
        "--user=demo-user",
    ]
    assert runner.calls[0][5] == f"--jobs={','.join(job_ids[:50])}"
    assert runner.calls[1][5] == "--jobs=51"
    assert all("--starttime=now-7days" not in call for call in runner.calls)


def test_native_adapter_rejects_unsafe_or_unbounded_targeted_job_ids() -> None:
    runner = RecordingRunner()
    adapter = NativeSlurmAdapter(runner)

    with pytest.raises(ValueError, match="Slurm job identifier"):
        adapter.list_accounting_by_job_ids("demo-user", ["21482;whoami"])
    with pytest.raises(ValueError, match="at most 100"):
        adapter.list_accounting_by_job_ids(
            "demo-user", [str(job_id) for job_id in range(SACCT_TARGET_MAX_JOB_IDS + 1)]
        )

    assert runner.calls == []


def test_native_adapter_targeted_accounting_filters_unrequested_and_other_owner_rows() -> None:
    runner = RecordingRunner(
        "21482|wanted|COMPLETED|demo-user|Students|stu|qos|node|0:0|||||\n"
        "21483|other-job|FAILED|demo-user|Students|stu|qos|node|1:0|||||\n"
        "21482|other-owner|FAILED|other-user|Students|stu|qos|node|1:0|||||\n"
    )
    adapter = NativeSlurmAdapter(runner)

    jobs = adapter.list_accounting_by_job_ids("demo-user", ["21482"])

    assert [(job.job_id, job.user, job.state) for job in jobs] == [
        ("21482", "demo-user", "COMPLETED")
    ]


def test_native_adapter_uses_structured_usage_query_and_validates_job_id() -> None:
    runner = RecordingRunner()
    adapter = NativeSlurmAdapter(runner)

    adapter.get_usage("21482")

    assert runner.calls == [
        [
            "sacct",
            "--noheader",
            "--parsable2",
            "--jobs=21482",
            "--format=JobIDRaw,JobName,State,Elapsed,Timelimit,AllocCPUS,ReqTRES,AllocTRES,MaxRSS,AveCPU,TotalCPU,ExitCode,TRESUsageInAve,TRESUsageInMax",
        ]
    ]
    with pytest.raises(ValueError, match="Slurm job identifier"):
        adapter.get_usage("21482;whoami")
    assert len(runner.calls) == 1


def test_runner_uses_safe_subprocess_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["arguments"] = arguments
        captured.update(kwargs)
        return subprocess.CompletedProcess(arguments, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = SubprocessCommandRunner(timeout_seconds=3).run(["squeue", "--noheader"])

    assert result.stdout == "ok"
    assert captured == {
        "arguments": ["squeue", "--noheader"],
        "shell": False,
        "capture_output": True,
        "text": True,
        "timeout": 3,
        "check": False,
    }


def test_runner_translates_missing_command(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(SlurmCommandNotFound, match="not installed"):
        SubprocessCommandRunner().run(["squeue"])


def test_runner_translates_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)

    with pytest.raises(SlurmCommandTimeout, match="timed out after 2s"):
        SubprocessCommandRunner(timeout_seconds=2).run(["sacct"])


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("Unable to contact slurm controller", "CONTROLLER_UNAVAILABLE"),
        ("Invalid account or account/partition combination specified", "ACCOUNT_POLICY"),
        ("Invalid qos specification", "QOS_POLICY"),
        ("Invalid partition name specified", "PARTITION_POLICY"),
        ("Requested node configuration is not available", "RESOURCE_POLICY"),
        ("Job violates accounting/QOS policy", "QOS_POLICY"),
        ("opaque scheduler rejection /private/path", "UNKNOWN"),
    ],
)
def test_slurm_failure_classification_is_bounded(stderr: str, expected: str) -> None:
    assert classify_slurm_failure(stderr) == expected


def test_slurm_failure_fingerprint_does_not_expose_output() -> None:
    fingerprint, output_length = fingerprint_slurm_failure(
        "stdout includes /private/source.py",
        "stderr includes secret-owner",
    )

    assert len(fingerprint) == 16
    assert fingerprint.isalnum()
    assert output_length == 63
    assert "private" not in fingerprint


def test_runner_translates_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 1, stdout="", stderr="access denied")

    monkeypatch.setattr(subprocess, "run", failed)

    with pytest.raises(SlurmCommandFailed, match="exited with 1: access denied") as error:
        SubprocessCommandRunner().run(["sinfo"])

    assert error.value.returncode == 1
    assert error.value.stderr == "access denied"
    assert error.value.category == "AUTHORIZATION"


def test_runner_classifies_failure_written_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            arguments,
            255,
            stdout="Unable to contact slurm controller",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", failed)

    with pytest.raises(SlurmCommandFailed) as error:
        SubprocessCommandRunner().run(["sbatch", "job.sh"])

    assert error.value.category == "CONTROLLER_UNAVAILABLE"
    assert error.value.returncode == 255
    assert error.value.output_length == 34


@pytest.mark.parametrize(
    ("os_error", "message"),
    [
        (PermissionError(13, "Permission denied"), "Permission denied"),
        (OSError(5, "I/O error"), "I/O error"),
    ],
)
def test_runner_translates_os_errors(
    monkeypatch: pytest.MonkeyPatch, os_error: OSError, message: str
) -> None:
    def fail_to_execute(*args: Any, **kwargs: Any) -> None:
        raise os_error

    monkeypatch.setattr(subprocess, "run", fail_to_execute)

    with pytest.raises(SlurmCommandExecutionError, match=message) as error:
        SubprocessCommandRunner().run(["squeue"])

    assert error.value.arguments == ("squeue",)
    assert error.value.os_error is os_error
