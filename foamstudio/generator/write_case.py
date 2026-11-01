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


def write_airfoil(
    project: Project,
    code: str,
    alpha_deg: float,
    reynolds: float,
    *,
    app_version: str,
    scale: float = 1.0,
    processes: int = 1,
) -> tuple[list[Path], str]:
    """NACA 4-digit case: C-mesh blockMeshDict, case.json with forces, then generator output."""
    import json

    from foamstudio.core.mesh.airfoil import airfoil_spec, c_mesh

    spec = airfoil_spec(code, alpha_deg, reynolds)
    spec["state"]["nProcs"] = processes
    spec_path = project.root / "airfoil.case.json"
    spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    paths, command = write_spec_file(project, spec_path, app_version=app_version)
    mesh = project.case_dir / "system" / "blockMeshDict"
    first = 4e-6 * (6e6 / reynolds) ** 0.9  # y+ ~ 0.5 at any Re: wall cell scales ~ Re^-0.9
    mesh.write_text(c_mesh(code, first, scale), encoding="utf-8", newline="\n")
    return [*paths, mesh], command
