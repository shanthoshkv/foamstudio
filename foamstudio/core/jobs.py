"""Tracked Allrun steps. Cancel kills the process tree on WSL and on the host."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from foamstudio.core.runtime.base import BoundRuntime
from foamstudio.core.runtime.model import CommandResult, Installation, RuntimeFailure, log_tail
from foamstudio.core.runtime.paths import launch_env
from foamstudio.core.runtime.probe import Completed, decode_output

MATRIX_ALLRUN = "./Allrun"


@dataclass
class Job:
    name: str
    command: str
    status: str = "pending"
    returncode: int | None = None
    log_tail: str = ""
    suggestion: str = ""


@dataclass
class JobQueue:
    runtime: BoundRuntime
    case: Path
    jobs: list[Job] = field(default_factory=list)
    pid: int | None = None
    _cancel: bool = False

    def add(self, command: str, *, name: str | None = None) -> Job:
        job = Job(name or command.split()[0], command)
        self.jobs.append(job)
        return job

    def add_allrun(
        self,
        solver: str,
        *,
        parallel: int = 1,
        mesh: str = "blockMesh",
    ) -> None:
        for command in allrun_commands(solver, parallel=parallel, mesh=mesh):
            self.add(command)

    def add_matrix(self) -> None:
        """The 225-case harness runs `./Allrun`. This is that same step."""
        self.add(MATRIX_ALLRUN, name="Allrun")

    def cancel(self) -> tuple[str, ...] | None:
        self._cancel = True
        for job in self.jobs:
            if job.status == "pending":
                job.status = "cancelled"
                job.suggestion = "Cancelled before this step started."
        if self.pid is None:
            return None
        argv = kill_argv(self.runtime.installation, self.pid, platform=sys.platform)
        return argv

    def run_blocking(self, *, live: bool = False) -> tuple[Job, ...]:
        return asyncio.run(self._run(live=live))

    async def _run(self, *, live: bool) -> tuple[Job, ...]:
        for job in self.jobs:
            if self._cancel or job.status == "cancelled":
                job.status = "cancelled"
                continue
            job.status = "running"
            try:
                if live:
                    result = self._run_live(job.command)
                else:
                    result = await self.runtime.run(job.command, self.case)
            except RuntimeFailure as exc:
                job.status = "failed"
                job.returncode = exc.returncode
                job.log_tail = exc.log_tail
                job.suggestion = exc.suggestion
                self._cancel = True
                continue
            job.status = "succeeded"
            job.returncode = result.returncode
            job.log_tail = result.log_tail
        return tuple(self.jobs)

    def _run_live(self, command: str) -> CommandResult:
        plan = self.runtime.prepare(command, self.case)
        last: Completed | None = None
        for step in plan.steps:
            proc = subprocess.Popen(
                list(step),
                cwd=str(self.case),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=launch_env(),
                start_new_session=sys.platform != "win32",
            )
            self.pid = proc.pid
            out, err = proc.communicate()
            stdout = decode_output(out)
            stderr = decode_output(err)
            code = 0 if proc.returncode is None else proc.returncode
            last = Completed(step, code, stdout, stderr)
            if code != 0:
                raise RuntimeFailure(
                    command=plan.display(),
                    returncode=code,
                    log_tail=log_tail(stdout, stderr),
                    suggestion="Read the log tail. The command above is the one FoamStudio ran.",
                )
        if last is None:
            raise RuntimeFailure(
                command=command,
                returncode=2,
                log_tail="(no output)",
                suggestion="The runtime produced no command.",
            )
        return CommandResult(
            last.argv,
            last.returncode,
            last.stdout,
            last.stderr,
            log_tail(last.stdout, last.stderr),
        )


def allrun_commands(solver: str, *, parallel: int = 1, mesh: str = "blockMesh") -> tuple[str, ...]:
    if not solver.strip():
        raise ValueError("The solver name is empty.")
    if parallel < 1:
        raise ValueError("The process count must be at least 1.")
    steps: list[str] = []
    if mesh == "blockMesh":
        steps.append("blockMesh")
    elif mesh == "snappyHexMesh":
        steps.extend(("blockMesh", "snappyHexMesh -overwrite"))
    elif mesh != "none":
        raise ValueError(f"Unknown mesh step {mesh!r}. Use blockMesh, snappyHexMesh, or none.")
    steps.append("checkMesh")
    if parallel > 1:
        steps.append("decomposePar")
        steps.append(f"mpirun -np {parallel} {solver} -parallel")
        steps.append("reconstructPar")
    else:
        steps.append(solver)
    return tuple(steps)


def kill_argv(installation: Installation, pid: int, *, platform: str) -> tuple[str, ...]:
    """Kill a solver process tree. WSL and SSH arguments do not contain `$VAR`."""
    if pid <= 0:
        raise ValueError(f"pid must be positive, got {pid}.")
    if installation.kind == "wsl":
        return (
            "wsl.exe",
            "-d",
            installation.distro,
            "--",
            "bash",
            "-lc",
            f"kill -- -{pid}",
        )
    if installation.kind == "ssh":
        return (
            "ssh",
            "-o",
            "BatchMode=yes",
            f"{installation.user}@{installation.host}",
            "bash",
            "-lc",
            f"kill -- -{pid}",
        )
    if platform == "win32":
        return ("taskkill", "/PID", str(pid), "/T", "/F")
    return ("kill", "--", f"-{pid}")
