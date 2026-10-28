"""foamstudio.json: versions, the command log, and git blob hashes of case files."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

MANIFEST_NAME = "foamstudio.json"
MANIFEST_SCHEMA = 1
_HEX40 = re.compile(r"[0-9a-f]{40}")


class ProvenanceError(Exception):
    """foamstudio.json cannot be read. The message includes a fix."""

    def __init__(self, message: str, *, suggestion: str) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"{message}\n\n{suggestion}")


def git_blob_hash(data: bytes) -> str:
    """Hash bytes the way ``git hash-object`` hashes a blob."""

    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CommandLogEntry:
    at: str
    command: str
    returncode: int

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at, "command": self.command, "returncode": self.returncode}


@dataclass
class Provenance:
    app_version: str
    generator_version: str
    openfoam_version: str | None = None
    runtime: dict[str, Any] | None = None
    commands: list[CommandLogEntry] = field(default_factory=list)
    inputs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema": MANIFEST_SCHEMA,
            "appVersion": self.app_version,
            "generatorVersion": self.generator_version,
            "commands": [entry.to_dict() for entry in self.commands],
            "inputs": dict(self.inputs),
        }
        if self.openfoam_version is not None:
            body["openfoamVersion"] = self.openfoam_version
        if self.runtime is not None:
            body["runtime"] = self.runtime
        return body


def load_provenance(path: Path) -> Provenance:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProvenanceError(
            f"Could not read {path}: {exc}",
            suggestion="Restore foamstudio.json, or create a new project folder.",
        ) from exc
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProvenanceError(
            f"{path} is not valid JSON: {exc}",
            suggestion="Restore foamstudio.json, or create a new project folder.",
        ) from exc
    if not isinstance(data, dict):
        raise ProvenanceError(
            f"{path} is not a JSON object.",
            suggestion="Restore foamstudio.json, or create a new project folder.",
        )
    return provenance_from_dict(cast(dict[str, Any], data))


def save_provenance(path: Path, provenance: Provenance) -> None:
    payload = json.dumps(provenance.to_dict(), indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    path.write_bytes(payload)


def provenance_from_dict(data: dict[str, Any]) -> Provenance:
    schema = data.get("schema")
    if schema != MANIFEST_SCHEMA:
        raise ProvenanceError(
            f"foamstudio.json schema {schema!r} is not supported.",
            suggestion=f"This build reads schema {MANIFEST_SCHEMA}. Create a new project folder.",
        )
    app_version = _require_str(data, "appVersion")
    generator_version = _require_str(data, "generatorVersion")
    openfoam = data.get("openfoamVersion")
    if openfoam is not None and not isinstance(openfoam, str):
        raise ProvenanceError(
            'foamstudio.json "openfoamVersion" must be a string when it is present.',
            suggestion="Leave openfoamVersion out until a case has been written.",
        )
    runtime = data.get("runtime")
    if runtime is not None and not isinstance(runtime, dict):
        raise ProvenanceError(
            'foamstudio.json "runtime" must be an object when it is present.',
            suggestion="Leave runtime out until a solver run records one.",
        )
    commands_raw = data.get("commands")
    if not isinstance(commands_raw, list):
        raise ProvenanceError(
            'foamstudio.json "commands" must be an array.',
            suggestion=(
                "Create a new project. A new foamstudio.json starts with an empty command log."
            ),
        )
    commands: list[CommandLogEntry] = []
    for index, item in enumerate(cast(list[object], commands_raw)):
        commands.append(_command(item, index))
    inputs_raw = data.get("inputs")
    if not isinstance(inputs_raw, dict):
        raise ProvenanceError(
            'foamstudio.json "inputs" must be an object of path to git blob hash.',
            suggestion="Create a new project. Inputs are filled in when a case is written.",
        )
    inputs: dict[str, str] = {}
    for key, digest in cast(dict[str, Any], inputs_raw).items():
        if (
            not isinstance(key, str)
            or not isinstance(digest, str)
            or _HEX40.fullmatch(digest) is None
        ):
            raise ProvenanceError(
                f"foamstudio.json inputs[{key!r}] is not a 40-character git blob hash.",
                suggestion="Write the case again. FoamStudio records hashes of the files it wrote.",
            )
        inputs[key] = digest
    return Provenance(
        app_version=app_version,
        generator_version=generator_version,
        openfoam_version=openfoam if isinstance(openfoam, str) else None,
        runtime=cast(dict[str, Any], runtime) if isinstance(runtime, dict) else None,
        commands=commands,
        inputs=inputs,
    )


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ProvenanceError(
            f'foamstudio.json "{key}" must be a non-empty string.',
            suggestion="Create a new project from File → New project.",
        )
    return value


def _command(item: object, index: int) -> CommandLogEntry:
    if not isinstance(item, dict):
        raise ProvenanceError(
            f"foamstudio.json commands[{index}] is not an object.",
            suggestion="Each command log entry needs at, command, and returncode.",
        )
    entry = cast(dict[str, Any], item)
    at = entry.get("at")
    command = entry.get("command")
    code = entry.get("returncode")
    if (
        not isinstance(at, str)
        or not isinstance(command, str)
        or isinstance(code, bool)
        or not isinstance(code, int)
    ):
        raise ProvenanceError(
            (
                f"foamstudio.json commands[{index}] needs a timestamp, a command, "
                "and an integer returncode."
            ),
            suggestion="Write the case again so FoamStudio appends a complete log entry.",
        )
    return CommandLogEntry(at=at, command=command, returncode=code)
