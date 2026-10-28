"""Write generator output into a project. The bytes come from the HTML generator."""

from __future__ import annotations

from pathlib import Path

from foamstudio.core.project import Project, write_case_files
from foamstudio.core.spec import load_spec
from foamstudio.generator.headless import apply_spec_text


def write_spec_file(
    project: Project,
    spec_path: Path,
    *,
    app_version: str,
    at: str | None = None,
) -> tuple[list[Path], str]:
    text = spec_path.read_text(encoding="utf-8-sig")
    spec = load_spec(text)
    case_name = str(spec["caseName"])
    generated = apply_spec_text(text, case_name=case_name, spec_path=spec_path)
    version = spec.get("openfoamVersion")
    paths = write_case_files(
        project,
        generated.files,
        case_name=case_name,
        command=generated.command,
        app_version=app_version,
        generator_version=str(spec["generator"]),
        openfoam_version=str(version) if version is not None else None,
        at=at,
    )
    return paths, generated.command
