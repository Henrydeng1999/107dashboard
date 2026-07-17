import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.slurm.adapter import FixtureSlurmAdapter, NativeSlurmAdapter
from app.slurm.runner import (
    CommandResult,
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


def test_native_adapter_uses_structured_usage_query_and_validates_job_id() -> None:
    runner = RecordingRunner()
    adapter = NativeSlurmAdapter(runner)

    adapter.get_usage("21482")

    assert runner.calls == [[
        "sacct",
        "--noheader",
        "--parsable2",
        "--jobs=21482",
        "--format=JobIDRaw,JobName,State,Elapsed,Timelimit,AllocCPUS,ReqTRES,AllocTRES,MaxRSS,AveCPU,TotalCPU,ExitCode,TRESUsageInAve,TRESUsageInMax",
    ]]
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


def test_runner_translates_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 1, stdout="", stderr="access denied")

    monkeypatch.setattr(subprocess, "run", failed)

    with pytest.raises(SlurmCommandFailed, match="exited with 1: access denied") as error:
        SubprocessCommandRunner().run(["sinfo"])

    assert error.value.returncode == 1
    assert error.value.stderr == "access denied"


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
