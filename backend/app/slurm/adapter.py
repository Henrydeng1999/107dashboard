import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from app.slurm.models import SlurmJob, SlurmPartition
from app.slurm.parsers import parse_sacct, parse_sinfo, parse_squeue
from app.slurm.runner import CommandResult, SubprocessCommandRunner

SQUEUE_FORMAT = "%i|%j|%T|%u|%P|%a|%q|%N|%r|%C|%m|%b|%l"
SACCT_FORMAT = (
    "JobIDRaw,JobName,State,User,Partition,Account,QOS,NodeList,ExitCode,"
    "ReqTRES,AllocTRES,Timelimit,Elapsed,Reason"
)
SINFO_FORMAT = "%P|%a|%t|%D|%C|%m|%G"
SACCT_HISTORY_START = "now-7days"
SACCT_HISTORY_END = "now"

_USER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}", re.ASCII)


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

    def list_partitions(self) -> list[SlurmPartition]: ...


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

    def list_partitions(self) -> list[SlurmPartition]:
        result = self.runner.run(["sinfo", "--noheader", f"--format={SINFO_FORMAT}"])
        return parse_sinfo(result.stdout)


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

    def list_partitions(self) -> list[SlurmPartition]:
        return parse_sinfo(self._read("sinfo.txt"))
