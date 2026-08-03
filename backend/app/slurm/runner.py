import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
import re


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


_SAFE_FAILURE_PATTERNS = (
    ("CONTROLLER_UNAVAILABLE", re.compile(r"unable to contact slurm controller|socket timed out|connection (?:refused|reset)|controller.*not responding", re.I)),
    ("ACCOUNT_POLICY", re.compile(r"invalid account|account/partition combination|accounting policy", re.I)),
    ("QOS_POLICY", re.compile(r"invalid qos|qos not permitted|qos specification|qos policy", re.I)),
    ("PARTITION_POLICY", re.compile(r"invalid partition|partition.*not (?:available|permitted|allowed)", re.I)),
    ("RESOURCE_POLICY", re.compile(r"requested node configuration is not available|invalid (?:generic resource|gres)|memory specification can not be satisfied", re.I)),
    ("SUBMISSION_LIMIT", re.compile(r"maximum number of jobs|job violates accounting/qos policy|association job limit", re.I)),
    ("AUTHORIZATION", re.compile(r"access denied|permission denied|not authorized|authentication", re.I)),
    ("TEMPORARY_FAILURE", re.compile(r"temporarily unavailable|resource temporarily unavailable|try again", re.I)),
)


def classify_slurm_failure(output: str) -> str:
    """Return a stable, non-sensitive category without exposing scheduler output."""
    for category, pattern in _SAFE_FAILURE_PATTERNS:
        if pattern.search(output):
            return category
    return "UNKNOWN"


def fingerprint_slurm_failure(stdout: str, stderr: str) -> tuple[str, int]:
    """Create a bounded correlation fingerprint without retaining scheduler output."""
    output = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
    return sha256(output.encode("utf-8", errors="replace")).hexdigest()[:16], len(output)


class SlurmCommandFailed(SlurmCommandError):
    def __init__(
        self,
        arguments: tuple[str, ...],
        returncode: int,
        stderr: str,
        stdout: str = "",
    ) -> None:
        detail = stderr.strip() or "no stderr output"
        super().__init__(f"Slurm command {arguments[0]} exited with {returncode}: {detail}")
        self.arguments = arguments
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        combined_output = "\n".join(part for part in (stdout, stderr) if part)
        self.category = classify_slurm_failure(combined_output)
        self.output_fingerprint, self.output_length = fingerprint_slurm_failure(stdout, stderr)


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
            raise SlurmCommandFailed(
                command,
                completed.returncode,
                completed.stderr,
                completed.stdout,
            )
        return CommandResult(stdout=completed.stdout, stderr=completed.stderr)
