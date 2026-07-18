from pathlib import Path

import pytest

from app.schemas.jobs import JobSubmitRequest
from app.slurm.runner import CommandResult
from app.slurm.submission import (
    NativeSlurmSubmitter,
    SubmissionValidationError,
    build_submission_plan,
    materialize_submission,
    parse_allowed_command,
    parse_sbatch_job_id,
    write_submission_receipt,
)


def submission(command: str = "python train.py --epochs 2", *, gpus: int = 1) -> JobSubmitRequest:
    return JobSubmitRequest.model_validate(
        {
            "name": "safe-job",
            "command": command,
            "partition": "Students",
            "account": "stu",
            "qos": "qos_stu_default",
            "resources": {
                "cpus": 2,
                "memory_mb": 4096,
                "gpus": gpus,
                "time_limit_minutes": 5,
            },
        }
    )


@pytest.mark.parametrize("command", ["python train.py --epochs 2", "python3 --version"])
def test_allowed_command_is_tokenized(command: str) -> None:
    assert parse_allowed_command(command)[0] in {"python", "python3"}


@pytest.mark.parametrize(
    "command",
    [
        "bash train.sh",
        "python train.py;id",
        "python train.py && id",
        "python $(id)",
        "python `id`",
        "python train.py | tee out",
        "python train.py > out",
        "python /tmp/train.py",
        "python ../train.py",
        "python --config=../secret",
        'python "unterminated',
    ],
)
def test_unsafe_commands_are_rejected(command: str) -> None:
    with pytest.raises(SubmissionValidationError):
        parse_allowed_command(command)


def test_plan_builds_structured_sbatch_arguments(tmp_path: Path) -> None:
    plan = build_submission_plan(
        submission(),
        owner="pb24030760",
        workspace_root=tmp_path,
        submission_id="submission-11111111111111111111111111111111",
    )
    assert plan.sbatch_arguments == (
        "sbatch",
        "--parsable",
        "--job-name=safe-job",
        "--partition=Students",
        "--account=stu",
        "--qos=qos_stu_default",
        "--nodes=1",
        "--ntasks=1",
        "--cpus-per-task=2",
        "--mem=4096M",
        "--time=5",
        "--gres=gpu:1",
        f"--chdir={plan.directory}",
        f"--output={plan.stdout_path}",
        f"--error={plan.stderr_path}",
        str(plan.script_path),
    )
    assert "#SBATCH" not in plan.script_text
    assert plan.script_text.endswith("exec python train.py --epochs 2\n")


def test_zero_gpu_omits_gres(tmp_path: Path) -> None:
    plan = build_submission_plan(
        submission(gpus=0), owner="owner", workspace_root=tmp_path
    )
    assert not any(argument.startswith("--gres=") for argument in plan.sbatch_arguments)


def test_plan_rejects_invalid_owner(tmp_path: Path) -> None:
    with pytest.raises(SubmissionValidationError):
        build_submission_plan(submission(), owner="other user", workspace_root=tmp_path)


@pytest.mark.parametrize(
    ("stdout", "expected"), [("21482\n", "21482"), ("21482;training\n", "21482")]
)
def test_parse_sbatch_job_id(stdout: str, expected: str) -> None:
    assert parse_sbatch_job_id(stdout) == expected


@pytest.mark.parametrize("stdout", ["", "0\n", "Submitted batch job 12\n", "12\n13\n", "12;bad cluster\n"])
def test_parse_sbatch_job_id_rejects_malformed_output(stdout: str) -> None:
    with pytest.raises(SubmissionValidationError):
        parse_sbatch_job_id(stdout)


def test_materialization_and_receipt_are_exclusive(tmp_path: Path) -> None:
    plan = build_submission_plan(submission(), owner="owner", workspace_root=tmp_path)
    materialize_submission(plan)
    assert plan.script_path.read_text(encoding="utf-8") == plan.script_text
    receipt = write_submission_receipt(plan, "21482")
    assert receipt.read_text(encoding="ascii") == "21482\n"
    with pytest.raises(FileExistsError):
        materialize_submission(plan)
    with pytest.raises(FileExistsError):
        write_submission_receipt(plan, "21482")


def test_submitter_uses_runner_without_shell_text(tmp_path: Path) -> None:
    class Runner:
        arguments: tuple[str, ...] | None = None

        def run(self, arguments: tuple[str, ...]) -> CommandResult:
            self.arguments = tuple(arguments)
            return CommandResult(stdout="21482;training\n", stderr="")

    runner = Runner()
    plan = build_submission_plan(submission(), owner="owner", workspace_root=tmp_path)
    assert NativeSlurmSubmitter(runner).submit(plan) == "21482"  # type: ignore[arg-type]
    assert runner.arguments == plan.sbatch_arguments
