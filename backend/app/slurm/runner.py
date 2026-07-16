import subprocess
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str


class SlurmCommandError(RuntimeError):
    """Base error for a failed Slurm client invocation."""


class SlurmCommandNotFound(SlurmCommandError):
    def __init__(self, executable: str) -> None:
        super().__init__(f"Slurm command is not installed or not on PATH: {executable}")
        self.executable = executable


class SlurmCommandTimeout(SlurmCommandError):
    def __init__(self, arguments: tuple[str, ...], timeout_seconds: float) -> None:
        super().__init__(f"Slurm command timed out after {timeout_seconds:g}s: {arguments[0]}")
        self.arguments = arguments
        self.timeout_seconds = timeout_seconds


class SlurmCommandFailed(SlurmCommandError):
    def __init__(self, arguments: tuple[str, ...], returncode: int, stderr: str) -> None:
        detail = stderr.strip() or "no stderr output"
        super().__init__(f"Slurm command {arguments[0]} exited with {returncode}: {detail}")
        self.arguments = arguments
        self.returncode = returncode
        self.stderr = stderr


class SlurmCommandExecutionError(SlurmCommandError):
    def __init__(self, arguments: tuple[str, ...], error: OSError) -> None:
        detail = error.strerror or str(error) or error.__class__.__name__
        super().__init__(f"Could not execute Slurm command {arguments[0]}: {detail}")
        self.arguments = arguments
        self.os_error = error


class SubprocessCommandRunner:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def run(self, arguments: Sequence[str]) -> CommandResult:
        command = tuple(arguments)
        if not command or any(not isinstance(argument, str) for argument in command):
            raise ValueError("arguments must be a non-empty sequence of strings")

        try:
            completed = subprocess.run(
                list(command),
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SlurmCommandNotFound(command[0]) from exc
        except subprocess.TimeoutExpired as exc:
            raise SlurmCommandTimeout(command, self.timeout_seconds) from exc
        except OSError as exc:
            raise SlurmCommandExecutionError(command, exc) from exc

        if completed.returncode != 0:
            raise SlurmCommandFailed(command, completed.returncode, completed.stderr)
        return CommandResult(stdout=completed.stdout, stderr=completed.stderr)
