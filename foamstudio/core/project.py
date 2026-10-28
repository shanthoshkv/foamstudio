"""A FoamStudio project is a folder with case/, geometry/, and foamstudio.json."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from foamstudio.core.provenance import (
    MANIFEST_NAME,
    CommandLogEntry,
    Provenance,
    ProvenanceError,
    git_blob_hash,
    load_provenance,
    save_provenance,
    utc_now,
)
from foamstudio.core.spec import GENERATOR_VERSION


class ProjectError(Exception):
    """A project folder cannot be created, opened, or written. The message includes a fix."""

    def __init__(self, message: str, *, suggestion: str) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"{message}\n\n{suggestion}")


@dataclass
class Project:
    root: Path
    provenance: Provenance

    @property
    def case_dir(self) -> Path:
        return self.root / "case"

    @property
    def geometry_dir(self) -> Path:
        return self.root / "geometry"

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_NAME


def create_project(
    root: Path,
    *,
    app_version: str,
    generator_version: str = GENERATOR_VERSION,
) -> Project:
    if not app_version:
        raise ProjectError(
            "The application version is empty.",
            suggestion="Install FoamStudio and create the project from that install.",
        )
    try:
        folder = root.resolve()
    except OSError as exc:
        raise ProjectError(
            f"Cannot use {root} as a project folder: {exc}",
            suggestion="Choose a local folder you can create.",
        ) from exc
    manifest = folder / MANIFEST_NAME
    if manifest.exists():
        raise ProjectError(
            f"{folder} is already a FoamStudio project.",
            suggestion=f"Open {folder} instead of creating a new project there.",
        )
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "case").mkdir(exist_ok=True)
        (folder / "geometry").mkdir(exist_ok=True)
    except OSError as exc:
        raise ProjectError(
            f"Cannot create the project folders in {folder}: {exc}",
            suggestion="Choose a folder you can write to.",
        ) from exc
    provenance = Provenance(app_version=app_version, generator_version=generator_version)
    try:
        save_provenance(manifest, provenance)
    except OSError as exc:
        raise ProjectError(
            f"Cannot write {manifest}: {exc}",
            suggestion="Choose a folder you can write to.",
        ) from exc
    return Project(folder, provenance)


def open_project(root: Path) -> Project:
    try:
        folder = root.resolve()
    except OSError as exc:
        raise ProjectError(
            f"Cannot open {root}: {exc}",
            suggestion="Choose the folder that contains foamstudio.json.",
        ) from exc
    if not folder.exists():
        raise ProjectError(
            f"{folder} does not exist.",
            suggestion=(
                "Create a project from File → New project, or choose an existing folder "
                "that contains foamstudio.json."
            ),
        )
    if not folder.is_dir():
        raise ProjectError(
            f"{folder} is not a folder.",
            suggestion="A project is a folder that contains foamstudio.json, case/, and geometry/.",
        )
    manifest = folder / MANIFEST_NAME
    if not manifest.is_file():
        raise ProjectError(
            f"No foamstudio.json in {folder}.",
            suggestion=(
                "Create a project from File → New project, or choose the folder that already "
                "contains foamstudio.json. A case directory alone is not a project."
            ),
        )
    try:
        provenance = load_provenance(manifest)
    except ProvenanceError as exc:
        raise ProjectError(exc.message, suggestion=exc.suggestion) from exc
    return Project(folder, provenance)


def write_case_files(
    project: Project,
    files: dict[str, str],
    *,
    case_name: str,
    command: str,
    app_version: str,
    generator_version: str,
    openfoam_version: str | None = None,
    returncode: int = 0,
    at: str | None = None,
) -> list[Path]:
    """Write generator output under ``project/case``, stripping the ``case_name/`` prefix."""

    if not files:
        raise ProjectError(
            "The generator returned no files.",
            suggestion="Check the solver and case.json. The log has the generator command.",
        )
    if not command.strip():
        raise ProjectError(
            "The case write has no command to record.",
            suggestion="Pass the Node or WebEngine command that produced these files.",
        )
    prefix = _case_prefix(case_name)
    case_root = project.case_dir
    try:
        case_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectError(
            f"Cannot create {case_root}: {exc}",
            suggestion="Choose a project folder you can write to.",
        ) from exc
    planned: list[tuple[Path, str, bytes]] = []
    rels: set[str] = set()
    for key, text in files.items():
        rel = _relative_case_path(key, prefix)
        rel_key = rel.as_posix()
        if rel_key in rels:
            raise ProjectError(
                f"The generator returned {key!r} twice.",
                suggestion=(
                    "Report this as a generator bug. The dictionary text is kept as written."
                ),
            )
        rels.add(rel_key)
        target = _inside_case(case_root, rel, key)
        planned.append((target, rel_key, text.encode("utf-8")))

    for rel_key in set(project.provenance.inputs) - rels:
        stale = _inside_case(case_root, Path(rel_key), rel_key)
        if stale.is_file():
            try:
                stale.unlink()
            except OSError as exc:
                raise ProjectError(
                    f"Cannot remove the previous file {stale}: {exc}",
                    suggestion="Close any program using that file and write the case again.",
                ) from exc
        project.provenance.inputs.pop(rel_key, None)

    written: list[Path] = []
    for target, rel_key, data in planned:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as exc:
            raise ProjectError(
                f"Cannot write {target}: {exc}",
                suggestion="Choose a project folder you can write to and write the case again.",
            ) from exc
        project.provenance.inputs[rel_key] = git_blob_hash(data)
        written.append(target)

    project.provenance.app_version = app_version
    project.provenance.generator_version = generator_version
    if openfoam_version is not None:
        project.provenance.openfoam_version = openfoam_version
    project.provenance.commands.append(
        CommandLogEntry(at=at or utc_now(), command=command, returncode=returncode)
    )
    try:
        save_provenance(project.manifest_path, project.provenance)
    except OSError as exc:
        raise ProjectError(
            f"Cannot update {project.manifest_path}: {exc}",
            suggestion="The case files were written. Fix the folder permissions and write again.",
        ) from exc
    return written


def _case_prefix(case_name: str) -> str:
    if (
        not case_name
        or case_name in {".", ".."}
        or "/" in case_name
        or "\\" in case_name
        or ":" in case_name
    ):
        raise ProjectError(
            f"Case name {case_name!r} cannot be used as a directory prefix.",
            suggestion=(
                "Use the caseName from case.json. It is a single folder name such as myCase."
            ),
        )
    return case_name + "/"


def _relative_case_path(key: str, prefix: str) -> Path:
    normalized = key.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("/") or ":" in normalized:
        raise ProjectError(
            f"Refusing to write {key!r} outside the case directory.",
            suggestion="Generator paths must stay inside the case name prefix.",
        )
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix) :]
    if not normalized or normalized.endswith("/"):
        raise ProjectError(
            f"Generator path {key!r} is not a file.",
            suggestion="buildCaseFiles should return file paths such as system/controlDict.",
        )
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ProjectError(
            f"Refusing to write {key!r} outside the case directory.",
            suggestion="Generator paths must stay inside the case name prefix.",
        )
    return path


def _inside_case(case_root: Path, relative: Path, key: str) -> Path:
    root = case_root.resolve()
    target = (root / relative).resolve()
    try:
        if os.path.commonpath((root, target)) != str(root):
            raise ProjectError(
                f"Refusing to write {key!r} outside the case directory.",
                suggestion="Generator paths must stay inside the case name prefix.",
            )
    except ValueError as exc:
        raise ProjectError(
            f"Refusing to write {key!r} outside the case directory.",
            suggestion="Generator paths must stay inside the case name prefix.",
        ) from exc
    return target
