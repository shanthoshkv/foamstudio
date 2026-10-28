"""Installations and the errors a runtime shows to the user."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

KINDS = ("native", "wsl", "docker", "ssh")
FLAVOURS = ("esi", "foundation")


@dataclass(frozen=True)
class Installation:
    kind: str
    flavour: str
    version: str
    bashrc: str
    distro: str = ""
    image: str = ""
    host: str = ""
    user: str = ""
    remote_case: str = ""
    scheduler: str = ""

    def label(self) -> str:
        if self.kind == "wsl":
            return f"{self.flavour} {self.version}  wsl {self.distro}"
        if self.kind == "docker":
            return f"{self.flavour} {self.version}  docker {self.image}"
        if self.kind == "ssh":
            return f"{self.flavour} {self.version}  ssh {self.user}@{self.host}"
        return f"{self.flavour} {self.version}  native"

    def to_dict(self) -> dict[str, str]:
        data = {
            "kind": self.kind,
            "flavour": self.flavour,
            "version": self.version,
            "bashrc": self.bashrc,
        }
        if self.kind == "wsl":
            data["distro"] = self.distro
        if self.kind == "docker":
            data["image"] = self.image
        if self.kind == "ssh":
            data["host"] = self.host
            data["user"] = self.user
            if self.remote_case:
                data["remote_case"] = self.remote_case
            if self.scheduler:
                data["scheduler"] = self.scheduler
        return data

    @staticmethod
    def from_dict(raw: object) -> Installation:
        if not isinstance(raw, dict):
            raise ValueError("Runtime record must be an object.")
        mapping = cast(dict[object, object], raw)

        def text(key: str, *, required: bool) -> str:
            value = mapping.get(key, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise ValueError(f"Runtime field {key} must be a string.")
            if required and not value.strip():
                raise ValueError(f"Runtime record is missing {key}.")
            return value.strip()

        kind = text("kind", required=True)
        if kind not in KINDS:
            raise ValueError(f"Unknown runtime kind {kind!r}. Expected one of {KINDS}.")
        flavour = text("flavour", required=True)
        if flavour not in FLAVOURS:
            raise ValueError(f"Unknown OpenFOAM flavour {flavour!r}. Expected one of {FLAVOURS}.")
        installation = Installation(
            kind=kind,
            flavour=flavour,
            version=text("version", required=True),
            bashrc=text("bashrc", required=True),
            distro=text("distro", required=False),
            image=text("image", required=False),
            host=text("host", required=False),
            user=text("user", required=False),
            remote_case=text("remote_case", required=False),
            scheduler=text("scheduler", required=False),
        )
        if kind == "wsl" and not installation.distro:
            raise ValueError("A WSL runtime record is missing distro.")
        if kind == "docker" and not installation.image:
            raise ValueError("A Docker runtime record is missing image.")
        if kind == "ssh" and not installation.host:
            raise ValueError("An ssh runtime record is missing host.")
        if kind == "ssh" and not installation.user:
            raise ValueError("An ssh runtime record is missing user.")
        return installation


@dataclass(frozen=True)
class DetectionReport:
    installations: tuple[Installation, ...]
    notes: tuple[str, ...]

    def to_dicts(self) -> list[dict[str, str]]:
        return [item.to_dict() for item in self.installations]


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    log_tail: str

    @property
    def command(self) -> str:
        return format_argv(self.argv)


class RuntimeFailure(Exception):
    """A subprocess failed. The message includes the command, the log tail, and a fix."""

    def __init__(
        self,
        *,
        command: str,
        returncode: int,
        log_tail: str,
        suggestion: str,
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.log_tail = log_tail
        self.suggestion = suggestion
        super().__init__(f"Command failed ({returncode}).\n{command}\n\n{log_tail}\n\n{suggestion}")


def format_argv(argv: tuple[str, ...] | list[str]) -> str:
    return " ".join(_quote(part) for part in argv)


def _quote(part: str) -> str:
    if part and all(ch not in part for ch in " \t\n\"'$\\"):
        return part
    return "'" + part.replace("'", "'\\''") + "'"


def log_tail(stdout: str, stderr: str, *, lines: int = 40) -> str:
    text = "\n".join(part.strip("\n") for part in (stdout, stderr) if part.strip())
    if not text:
        return "(no output)"
    return "\n".join(text.splitlines()[-lines:])


def suggestion_for(*, kind: str, stderr: str, returncode: int) -> str:
    low = stderr.lower()
    if returncode == 127 or "command not found" in low or "no such file or directory" in low:
        return (
            "OpenFOAM did not provide this command. Confirm the bashrc path on the runtime, "
            "or install that OpenFOAM version and detect runtimes again."
        )
    if "docker" in low and ("daemon" in low or "cannot connect" in low or "pipe" in low):
        return "Start Docker and run the command again."
    if kind == "wsl" and (
        "0x800" in low or "not installed" in low or "wsl" in low and "error" in low
    ):
        return "Install WSL2 with: wsl --install -d Ubuntu-24.04"
    if kind == "ssh" and (
        "permission denied" in low or "host key" in low or "could not resolve" in low
    ):
        return (
            "Check the SSH host, user, and key. "
            "FoamStudio uses ssh -o BatchMode=yes and does not prompt."
        )
    if "permission denied" in low:
        return (
            "The case directory is not executable from this runtime. "
            "Check the mount and permissions."
        )
    return "Read the log tail. The command above is the one FoamStudio ran."
