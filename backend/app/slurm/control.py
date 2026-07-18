import re
from typing import Protocol

from app.slurm.runner import SubprocessCommandRunner


class SlurmCanceller(Protocol):
    def cancel(self, job_id: str) -> None: ...


class NativeSlurmCanceller:
    def __init__(self, runner: SubprocessCommandRunner) -> None:
        self._runner = runner

    def cancel(self, job_id: str) -> None:
        if re.fullmatch(r"[1-9][0-9]*", job_id, re.ASCII) is None:
            raise ValueError("job_id must be one numeric Slurm allocation ID")
        self._runner.run(("scancel", job_id))
