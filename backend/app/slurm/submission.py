import os
import re
import shlex
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from app.schemas.jobs import JobSubmitRequest
from app.slurm.runner import CommandResult, SubprocessCommandRunner
from app.services.test_projects import TestProject, TestProjectCatalog, TestProjectError


class SubmissionValidationError(ValueError):
    """Raised before any filesystem or Slurm write when a submission is unsafe."""


_SAFE_EXECUTABLES = frozenset({"python", "python3"})
_SAFE_ARGUMENT = re.compile(r"[A-Za-z0-9_./:=+,@%-]{1,128}", re.ASCII)
_SAFE_OWNER = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}", re.ASCII)
_SLURM_JOB_ID = re.compile(r"(?P<job_id>[1-9][0-9]*)(?:;[A-Za-z0-9._-]+)?\n?", re.ASCII)
_MAX_ARGUMENTS = 32


def parse_allowed_command(command: str) -> tuple[str, ...]:
    """Parse a deliberately narrow command language; shell syntax is never accepted."""
    try:
        arguments = tuple(shlex.split(command, posix=True))
    except ValueError as exc:
        raise SubmissionValidationError("command quoting is invalid") from exc
    if not arguments or arguments[0] not in _SAFE_EXECUTABLES:
        raise SubmissionValidationError("command executable is not allowed")
    if len(arguments) > _MAX_ARGUMENTS:
        raise SubmissionValidationError(f"command exceeds {_MAX_ARGUMENTS} arguments")
    for argument in arguments:
        if _SAFE_ARGUMENT.fullmatch(argument) is None:
            raise SubmissionValidationError("command contains an unsafe argument")
        path_value = argument.split("=", 1)[-1]
        path_variants = (PurePosixPath(path_value), PureWindowsPath(path_value))
        if any(path.is_absolute() or ".." in path.parts for path in path_variants):
            raise SubmissionValidationError("absolute paths and parent traversal are not allowed")
    return arguments


def render_allowed_command(arguments: tuple[str, ...]) -> str:
    if parse_allowed_command(shlex.join(arguments)) != arguments:
        raise SubmissionValidationError("command arguments do not round-trip safely")
    return shlex.join(arguments)


@dataclass(frozen=True, slots=True)
class SubmissionPlan:
    submission_id: str
    owner: str
    request: JobSubmitRequest
    arguments: tuple[str, ...]
    directory: Path
    script_path: Path
    stdout_path: Path
    stderr_path: Path
    project: TestProject | None = None

    @property
    def script_text(self) -> str:
        arguments = (
            ("python3", f"source/{self.project.entrypoint}")
            if self.project is not None
            else self.arguments
        )
        return "#!/usr/bin/env bash\nset -euo pipefail\nexec " + render_allowed_command(arguments) + "\n"

    @property
    def sbatch_arguments(self) -> tuple[str, ...]:
        resources = self.request.resources
        command = [
            "sbatch",
            "--parsable",
            f"--job-name={self.request.name}",
            f"--partition={self.request.partition}",
            f"--account={self.request.account}",
            f"--qos={self.request.qos}",
            "--nodes=1",
            "--ntasks=1",
            f"--cpus-per-task={resources.cpus}",
            f"--mem={resources.memory_mb}M",
            f"--time={resources.time_limit_minutes}",
        ]
        if resources.gpus:
            command.append(f"--gres=gpu:{resources.gpus}")
        command.extend(
            [
                f"--chdir={self.directory}",
                f"--output={self.stdout_path}",
                f"--error={self.stderr_path}",
                str(self.script_path),
            ]
        )
        return tuple(command)


def build_submission_plan(
    request: JobSubmitRequest,
    *,
    owner: str,
    workspace_root: Path,
    submission_id: str | None = None,
    project_catalog: TestProjectCatalog | None = None,
) -> SubmissionPlan:
    arguments = parse_allowed_command(request.command)
    project = None
    if len(arguments) == 2 and arguments[0] == "python3" and arguments[1].startswith("@project/"):
        if project_catalog is None:
            raise SubmissionValidationError("registered test projects are unavailable")
        try:
            project = project_catalog.get(arguments[1].removeprefix("@project/"))
        except TestProjectError as exc:
            raise SubmissionValidationError("registered test project is invalid") from exc
    if _SAFE_OWNER.fullmatch(owner) is None:
        raise SubmissionValidationError("submission owner is invalid")
    root = workspace_root.resolve()
    identifier = submission_id or f"submission-{uuid4().hex}"
    if re.fullmatch(r"submission-[a-f0-9]{32}", identifier, re.ASCII) is None:
        raise SubmissionValidationError("submission identifier is invalid")
    directory = (root / identifier).resolve()
    if not directory.is_relative_to(root):
        raise SubmissionValidationError("submission directory escapes workspace")
    return SubmissionPlan(
        submission_id=identifier,
        owner=owner,
        request=request,
        arguments=arguments,
        directory=directory,
        script_path=directory / "job.sh",
        stdout_path=directory / "stdout.log",
        stderr_path=directory / "stderr.log",
        project=project,
    )


def materialize_submission(plan: SubmissionPlan) -> None:
    plan.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    if plan.project is not None:
        source_directory = plan.directory / "source"
        source_directory.mkdir(mode=0o700)
        target = source_directory / plan.project.entrypoint
        source_descriptor = os.open(plan.project.source_path, os.O_RDONLY | os.O_NOFOLLOW)
        source_metadata = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_metadata.st_mode) or source_metadata.st_size > 64 * 1024:
            os.close(source_descriptor)
            raise SubmissionValidationError("registered test project source changed unsafely")
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(source_descriptor, "rb") as source, os.fdopen(descriptor, "wb") as output:
            shutil.copyfileobj(source, output, length=64 * 1024)
            output.flush()
            os.fsync(output.fileno())
    descriptor = os.open(plan.script_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(plan.script_text)
        stream.flush()
        os.fsync(stream.fileno())
    plan.script_path.chmod(0o700)


def parse_sbatch_job_id(stdout: str) -> str:
    match = _SLURM_JOB_ID.fullmatch(stdout)
    if match is None:
        raise SubmissionValidationError("sbatch returned an invalid job identifier")
    return match.group("job_id")


def write_submission_receipt(plan: SubmissionPlan, slurm_job_id: str) -> Path:
    if re.fullmatch(r"[1-9][0-9]*", slurm_job_id, re.ASCII) is None:
        raise SubmissionValidationError("Slurm job identifier is invalid")
    receipt = plan.directory / "slurm-job-id"
    descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
        stream.write(slurm_job_id + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return receipt


class NativeSlurmSubmitter:
    def __init__(self, runner: SubprocessCommandRunner) -> None:
        self._runner = runner

    def submit(self, plan: SubmissionPlan) -> str:
        result: CommandResult = self._runner.run(plan.sbatch_arguments)
        return parse_sbatch_job_id(result.stdout)
