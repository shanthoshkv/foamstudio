"""One runtime interface over native, WSL, and Docker."""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from foamstudio.core.runtime.docker import detect_docker
from foamstudio.core.runtime.model import (
    CommandResult,
    DetectionReport,
    Installation,
    RuntimeFailure,
    format_argv,
    log_tail,
    suggestion_for,
)
from foamstudio.core.runtime.native import detect_native
from foamstudio.core.runtime.paths import (
    bash_command,
    host_text,
    launch_env,
    strip_zone_identifiers,
    windows_to_wsl,
    write_runner,
)
from foamstudio.core.runtime.probe import Probe, SubprocessProbe
from foamstudio.core.runtime.wsl import detect_wsl, script_mount, wsl_steps

logger = logging.getLogger("foamstudio.runtime")

DETECT_TIMEOUT = 15.0
RUN_TIMEOUT = 120.0


@dataclass(frozen=True)
class RunPlan:
    steps: tuple[tuple[str, ...], ...]
    body: str
    script: Path | None = None

    def display(self) -> str:
        lines = [f"MSYS_NO_PATHCONV=1 {format_argv(step)}" for step in self.steps]
        if self.script is not None:
            lines.append("")
            lines.append(self.body)
        return "\n".join(lines)


class BoundRuntime:
    def __init__(self, installation: Installation, probe: Probe) -> None:
        self.installation = installation
        self._probe = probe

    def version(self) -> str:
        return self.installation.version

    def plan(
        self,
        command: str,
        case: Path,
        env: dict[str, str] | None = None,
        *,
        script: Path | None = None,
    ) -> RunPlan:
        kind = self.installation.kind
        if kind == "native":
            directory = host_text(case)
            body = bash_command(self.installation.bashrc, directory, command, env)
            return RunPlan((("bash", "-lc", body),), body)
        if kind == "docker":
            directory = "/case"
            body = bash_command(self.installation.bashrc, directory, command, env)
            host = host_text(case)
            _reject_mount(host)
            argv = (
                "docker",
                "run",
                "--rm",
                "-v",
                f"{host}:/case",
                "-w",
                "/case",
                self.installation.image,
                "bash",
                "-lc",
                body,
            )
            return RunPlan((argv,), body)
        if kind == "wsl":
            if script is None:
                script = case / ".foamstudio" / "run.sh"
            mounted_case = windows_to_wsl(host_text(case))
            body = "#!/bin/bash\n" + bash_command(
                self.installation.bashrc, mounted_case, command, env
            )
            mounted_script = script_mount(script)
            steps = wsl_steps(self.installation.distro, mounted_script)
            return RunPlan(steps, body, script)
        if kind == "ssh":
            from foamstudio.core.runtime.ssh import ssh_argv

            try:
                remote_argv, body = ssh_argv(self.installation, command, env)
            except ValueError as exc:
                raise RuntimeFailure(
                    command=command,
                    returncode=2,
                    log_tail="(no output)",
                    suggestion=str(exc),
                ) from exc
            return RunPlan((remote_argv,), body)
        raise RuntimeFailure(
            command=command,
            returncode=2,
            log_tail="(no output)",
            suggestion=f"Unknown runtime kind {kind!r}.",
        )

    def describe(self, command: str, case: Path, env: dict[str, str] | None = None) -> str:
        return self.plan(command, case, env).display()

    def prepare(
        self,
        command: str,
        case: Path,
        env: dict[str, str] | None = None,
    ) -> RunPlan:
        """Build the exact argv, writing the WSL script when that transport is used."""
        if not case.is_dir():
            raise RuntimeFailure(
                command=command,
                returncode=2,
                log_tail="(no output)",
                suggestion=f"Create the case directory first: {case}",
            )
        removed = strip_zone_identifiers(case)
        if removed:
            logger.info("Removed Zone.Identifier files: %s", ", ".join(map(str, removed)))
        script: Path | None = None
        if self.installation.kind == "wsl":
            preview = self.plan(command, case, env)
            script = write_runner(case, preview.body.removeprefix("#!/bin/bash\n"))
            strip_zone_identifiers(case)
        return self.plan(command, case, env, script=script)

    async def execute(
        self,
        plan: RunPlan,
        *,
        case: Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        logger.info("Running %s", plan.display())
        limit = RUN_TIMEOUT if timeout is None else timeout
        child_env = launch_env(env)
        last: CommandResult | None = None
        for step in plan.steps:
            last = await asyncio.to_thread(self._one, step, case, child_env, limit, plan)
        if last is None:
            raise RuntimeFailure(
                command=plan.display(),
                returncode=2,
                log_tail="(no output)",
                suggestion="The runtime produced no command.",
            )
        return last

    async def run(
        self,
        command: str,
        case: Path,
        env: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> CommandResult:
        plan = self.prepare(command, case, env)
        return await self.execute(plan, case=case, env=env, timeout=timeout)

    def _one(
        self,
        argv: tuple[str, ...],
        case: Path,
        env: dict[str, str],
        timeout: float,
        plan: RunPlan,
    ) -> CommandResult:
        try:
            completed = self._probe.run(argv, cwd=case, env=env, timeout=timeout)
        except TimeoutError as exc:
            raise RuntimeFailure(
                command=plan.display(),
                returncode=124,
                log_tail=str(exc),
                suggestion=f"The command exceeded {timeout}s. It may be waiting for input.",
            ) from exc
        result = CommandResult(
            argv=completed.argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            log_tail=log_tail(completed.stdout, completed.stderr),
        )
        if result.returncode != 0:
            raise RuntimeFailure(
                command=plan.display(),
                returncode=result.returncode,
                log_tail=result.log_tail,
                suggestion=suggestion_for(
                    kind=self.installation.kind,
                    stderr=result.stderr,
                    returncode=result.returncode,
                ),
            )
        return result


def bind(installation: Installation, probe: Probe | None = None) -> BoundRuntime:
    return BoundRuntime(installation, probe or SubprocessProbe())


def detect(
    probe: Probe | None = None,
    *,
    platform: str | None = None,
    native_roots: tuple[Path, ...] | None = None,
    timeout: float = DETECT_TIMEOUT,
) -> DetectionReport:
    tool = probe or SubprocessProbe()
    system = sys.platform if platform is None else platform
    notes: list[str] = []
    found: list[Installation] = list(detect_native(native_roots))
    if system == "win32":
        wsl_found, wsl_notes = detect_wsl(tool, timeout=timeout)
        found.extend(wsl_found)
        notes.extend(wsl_notes)
    images, docker_notes = detect_docker(tool, timeout=timeout)
    found.extend(images)
    notes.extend(docker_notes)
    return DetectionReport(tuple(found), tuple(notes))


def _reject_mount(host: str) -> None:
    if "$" in host:
        raise ValueError(
            f"The case path contains '$' ({host}). Rename the folder before Docker mounts it."
        )
