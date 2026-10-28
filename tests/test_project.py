from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from foamstudio.core.project import ProjectError, create_project, open_project, write_case_files
from foamstudio.core.provenance import git_blob_hash, load_provenance
from foamstudio.core.spec import GENERATOR_VERSION, SpecError, load_spec, parse_spec


def _spec() -> dict[str, object]:
    return {
        "schema": 1,
        "generator": "2.2.0",
        "openfoamVersion": 2412,
        "caseName": "myCase",
        "state": {"solver": "simpleFoam", "patches": [{"name": "inlet", "role": "inlet"}]},
    }


def test_git_blob_hash_matches_git() -> None:
    assert git_blob_hash(b"hello") == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"


def test_generator_version_matches_html() -> None:
    html = (Path(__file__).parents[1] / "openfoam_case_generator.html").read_text(encoding="utf-8")
    match = re.search(r"const GEN_VERSION = '([^']+)'", html)
    assert match is not None
    assert match.group(1) == GENERATOR_VERSION


def test_create_open_and_missing_manifest(tmp_path: Path) -> None:
    root = tmp_path / "study"
    project = create_project(root, app_version="0.3.0")
    assert project.root == root.resolve()
    assert (root / "case").is_dir()
    assert (root / "geometry").is_dir()
    assert (root / "foamstudio.json").is_file()
    opened = open_project(root)
    assert opened.provenance.app_version == "0.3.0"
    assert opened.provenance.generator_version == GENERATOR_VERSION
    assert opened.provenance.commands == []
    with pytest.raises(ProjectError, match="already a FoamStudio project"):
        create_project(root, app_version="0.3.0")
    with pytest.raises(ProjectError, match="foamstudio.json") as missing:
        open_project(tmp_path / "absent")
    assert "New project" in missing.value.suggestion


def test_bad_manifest_is_loud(tmp_path: Path) -> None:
    root = tmp_path / "study"
    root.mkdir()
    (root / "foamstudio.json").write_text("{", encoding="utf-8")
    with pytest.raises(ProjectError, match="not valid JSON"):
        open_project(root)


def test_schema_migration_rejects_unknown_schema() -> None:
    with pytest.raises(SpecError, match="schema 2"):
        parse_spec({"schema": 2})
    with pytest.raises(SpecError, match="schema True|schema true"):
        parse_spec({"schema": True})


def test_structural_spec_checks_do_not_name_solvers() -> None:
    spec = _spec()
    assert load_spec(json.dumps(spec))["state"]["solver"] == "simpleFoam"  # type: ignore[index]
    spec["state"] = {"solver": "notARealSolver", "patches": []}  # type: ignore[index]
    parsed = parse_spec(spec)
    assert parsed["state"]["solver"] == "notARealSolver"  # type: ignore[index]


def test_write_case_strips_prefix_and_records_the_command(tmp_path: Path) -> None:
    project = create_project(tmp_path / "study", app_version="0.3.0")
    (project.case_dir / "mesh.msh").write_text("keep", encoding="utf-8")
    previous = {"myCase/system/stale": "old\n"}
    write_case_files(
        project,
        previous,
        case_name="myCase",
        command="node tests/headless.js --apply-spec old.json",
        app_version="0.3.0",
        generator_version="2.2.0",
        openfoam_version="2412",
        at="2026-10-27T00:00:00Z",
    )
    files = {
        "myCase/system/controlDict": "FoamFile\n{}\n",
        "myCase/case.json": "{}\n",
    }
    written = write_case_files(
        project,
        files,
        case_name="myCase",
        command="node tests/headless.js --apply-spec case.json --name myCase",
        app_version="0.3.0",
        generator_version="2.2.0",
        openfoam_version="2412",
        at="2026-10-27T00:00:01Z",
    )
    assert (project.case_dir / "system" / "controlDict").read_text(
        encoding="utf-8"
    ) == "FoamFile\n{}\n"
    assert not (project.case_dir / "system" / "stale").exists()
    assert (project.case_dir / "mesh.msh").read_text(encoding="utf-8") == "keep"
    assert len(written) == 2
    saved = load_provenance(project.manifest_path)
    assert saved.inputs["system/controlDict"] == git_blob_hash(b"FoamFile\n{}\n")
    assert "system/stale" not in saved.inputs
    assert saved.commands[-1].command.endswith("--name myCase")
    assert saved.commands[-1].at == "2026-10-27T00:00:01Z"
    assert saved.openfoam_version == "2412"
    assert b"\r" not in (project.manifest_path).read_bytes()


def test_write_refuses_parent_paths(tmp_path: Path) -> None:
    project = create_project(tmp_path / "study", app_version="0.3.0")
    with pytest.raises(ProjectError, match="outside the case"):
        write_case_files(
            project,
            {"myCase/../../foamstudio.json": "nope"},
            case_name="myCase",
            command="node tests/headless.js --apply-spec case.json",
            app_version="0.3.0",
            generator_version="2.2.0",
        )
