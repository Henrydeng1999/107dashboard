import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from app.slurm.models import SlurmJob, SlurmPartition, SlurmUsageRecord
from app.slurm.parsers import parse_sacct, parse_sacct_usage, parse_sinfo, parse_squeue
from app.slurm.runner import CommandResult, SubprocessCommandRunner

SQUEUE_FORMAT = "%i|%j|%T|%u|%P|%a|%q|%N|%r|%C|%m|%b|%l"
SACCT_FORMAT = (
    "JobIDRaw,JobName,State,User,Partition,Account,QOS,NodeList,ExitCode,"
    "ReqTRES,AllocTRES,Timelimit,Elapsed,Reason"
)
SINFO_FORMAT = "%P|%a|%t|%D|%C|%m|%G"
SACCT_HISTORY_START = "now-7days"
SACCT_HISTORY_END = "now"
SACCT_TARGET_BATCH_SIZE = 50
SACCT_TARGET_MAX_JOB_IDS = 100
SACCT_USAGE_FORMAT = (
    "JobIDRaw,JobName,State,Elapsed,Timelimit,AllocCPUS,ReqTRES,AllocTRES,"
    "MaxRSS,AveCPU,TotalCPU,ExitCode,TRESUsageInAve,TRESUsageInMax"
)

_USER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}", re.ASCII)
_JOB_ID_PATTERN = re.compile(r"\d+(?:[._+][A-Za-z0-9_-]+)*")


def _validate_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or _JOB_ID_PATTERN.fullmatch(job_id) is None:
        raise ValueError("job_id must be one Slurm job identifier")
    return job_id


def _validate_user(user: str) -> str:
    if not isinstance(user, str) or _USER_PATTERN.fullmatch(user) is None:
        raise ValueError(
            "user must be one platform username (1-32 ASCII letters, digits, '_' or '-', "
            "starting with a letter or '_')"
        )
    return user


class CommandRunner(Protocol):
    def run(self, arguments: Sequence[str]) -> CommandResult: ...


class SlurmAdapter(Protocol):
    def list_queue(self, user: str) -> list[SlurmJob]: ...

    def list_accounting(self, user: str) -> list[SlurmJob]: ...

    def list_accounting_by_job_ids(self, user: str, job_ids: Sequence[str]) -> list[SlurmJob]: ...

    def list_partitions(self) -> list[SlurmPartition]: ...

    def get_usage(self, job_id: str) -> list[SlurmUsageRecord]: ...


class NativeSlurmAdapter:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessCommandRunner()

    def list_queue(self, user: str) -> list[SlurmJob]:
        user = _validate_user(user)
        result = self.runner.run(
            ["squeue", "--noheader", "--array", f"--user={user}", f"--format={SQUEUE_FORMAT}"]
        )
        return parse_squeue(result.stdout)

    def list_accounting(self, user: str) -> list[SlurmJob]:
        user = _validate_user(user)
        result = self.runner.run(
            [
                "sacct",
                "--noheader",
                "--parsable2",
                "--allocations",
                f"--user={user}",
                f"--starttime={SACCT_HISTORY_START}",
                f"--endtime={SACCT_HISTORY_END}",
                f"--format={SACCT_FORMAT}",
            ]
        )
        return parse_sacct(result.stdout)

    def list_accounting_by_job_ids(self, user: str, job_ids: Sequence[str]) -> list[SlurmJob]:
        user = _validate_user(user)
        unique_job_ids = tuple(dict.fromkeys(_validate_job_id(job_id) for job_id in job_ids))
        if len(unique_job_ids) > SACCT_TARGET_MAX_JOB_IDS:
            raise ValueError(
                f"targeted accounting query accepts at most {SACCT_TARGET_MAX_JOB_IDS} job IDs"
            )
        jobs: list[SlurmJob] = []
        requested = set(unique_job_ids)
        for offset in range(0, len(unique_job_ids), SACCT_TARGET_BATCH_SIZE):
            batch = unique_job_ids[offset : offset + SACCT_TARGET_BATCH_SIZE]
            result = self.runner.run(
                [
                    "sacct",
                    "--noheader",
                    "--parsable2",
                    "--allocations",
                    f"--user={user}",
                    f"--jobs={','.join(batch)}",
                    f"--format={SACCT_FORMAT}",
                ]
            )
            jobs.extend(
                job
                for job in parse_sacct(result.stdout)
                if job.user == user and job.job_id in requested
            )
        return jobs

    def list_partitions(self) -> list[SlurmPartition]:
        result = self.runner.run(["sinfo", "--noheader", f"--format={SINFO_FORMAT}"])
        return parse_sinfo(result.stdout)

    def get_usage(self, job_id: str) -> list[SlurmUsageRecord]:
        _validate_job_id(job_id)
        result = self.runner.run(
            [
                "sacct",
                "--noheader",
                "--parsable2",
                f"--jobs={job_id}",
                f"--format={SACCT_USAGE_FORMAT}",
            ]
        )
        return parse_sacct_usage(result.stdout)


class FixtureSlurmAdapter:
    def __init__(self, fixture_directory: Path | str) -> None:
        self.fixture_directory = Path(fixture_directory)

    def _read(self, filename: str) -> str:
        return (self.fixture_directory / filename).read_text(encoding="utf-8")

    def list_queue(self, user: str) -> list[SlurmJob]:
        user = _validate_user(user)
        return [job for job in parse_squeue(self._read("squeue.txt")) if job.user == user]

    def list_accounting(self, user: str) -> list[SlurmJob]:
        user = _validate_user(user)
        return [job for job in parse_sacct(self._read("sacct.txt")) if job.user == user]

    def list_accounting_by_job_ids(self, user: str, job_ids: Sequence[str]) -> list[SlurmJob]:
        user = _validate_user(user)
        unique_job_ids = tuple(dict.fromkeys(_validate_job_id(job_id) for job_id in job_ids))
        if len(unique_job_ids) > SACCT_TARGET_MAX_JOB_IDS:
            raise ValueError(
                f"targeted accounting query accepts at most {SACCT_TARGET_MAX_JOB_IDS} job IDs"
            )
        requested = set(unique_job_ids)
        return [
            job
            for job in parse_sacct(self._read("sacct.txt"))
            if job.user == user and job.job_id in requested
        ]

    def list_partitions(self) -> list[SlurmPartition]:
        return parse_sinfo(self._read("sinfo.txt"))

    def get_usage(self, job_id: str) -> list[SlurmUsageRecord]:
        _validate_job_id(job_id)
        return [
            record
            for record in parse_sacct_usage(self._read("sacct_usage.txt"))
            if record.job_id == job_id or record.job_id.startswith(f"{job_id}.")
        ]
