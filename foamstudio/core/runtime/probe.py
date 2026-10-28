"""How a runtime talks to the operating system. Tests pass a fake."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ProbeMissing(FileNotFoundError):
    def __init__(self, program: str) -> None:
        self.program = program
        super().__init__(f"{program} was not found on PATH.")


@dataclass(frozen=True)
class Completed:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class Probe(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Completed: ...


def decode_output(data: bytes) -> str:
    """WSL list output is UTF-16. Everything else from these tools is UTF-8."""
    if not data:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data[:8]:
        return data.decode("utf-16").replace("\x00", "")
    return data.decode("utf-8", errors="replace")


class SubprocessProbe:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Completed:
        command = tuple(argv)
        try:
            finished = subprocess.run(
                list(command),
                cwd=str(cwd) if cwd is not None else None,
                env=dict(env) if env is not None else None,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial_out = decode_output(exc.stdout or b"")
            partial_err = decode_output(exc.stderr or b"")
            raise TimeoutError(
                f"{' '.join(command)} exceeded {timeout}s.\n{partial_out}\n{partial_err}".strip()
            ) from exc
        except FileNotFoundError as exc:
            raise ProbeMissing(command[0]) from exc
        return Completed(
            command,
            finished.returncode,
            decode_output(finished.stdout),
            decode_output(finished.stderr),
        )
