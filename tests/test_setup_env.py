import sys
from pathlib import Path

import pytest

from foamstudio.core import setup_env
from foamstudio.core.runtime.paths import unc_to_wsl, windows_to_wsl


def test_unc_paths() -> None:
    assert unc_to_wsl(r"\\wsl.localhost\Ubuntu\home\me\c") == ("Ubuntu", "/home/me/c")
    assert unc_to_wsl("//wsl$/Ubuntu") == ("Ubuntu", "/")
    assert (
        windows_to_wsl(r"\\wsl.localhost\U\home\me\c\.foamstudio\r.sh")
        == "/home/me/c/.foamstudio/r.sh"
    )


def test_check_libs_reports_each_requirement() -> None:
    rows = setup_env.check_libs(Path(sys.executable))
    assert [r for r, _ in rows] == list(setup_env.requirements())
    assert dict(rows)[next(r for r in setup_env.requirements() if r.startswith("numpy"))]


def test_installation_from_folder(tmp_path: Path) -> None:
    root = tmp_path / "my-foam"
    (root / "etc").mkdir(parents=True)
    (root / "etc" / "bashrc").write_text("export WM_PROJECT_VERSION=v2406\n")
    if sys.platform == "win32":
        with pytest.raises(ValueError):
            setup_env.installation_from_folder(str(root))
        return
    found = setup_env.installation_from_folder(str(root))
    assert (found.kind, found.flavour, found.version) == ("native", "esi", "2406")


def test_assist_helpers(tmp_path: Path) -> None:
    from foamstudio.core.assist import explain_foam_error, git_snapshot, validate_case

    assert "inlet" in explain_foam_error("--> FOAM FATAL\nCannot find patchField entry for inlet")
    assert explain_foam_error("all good") == ""
    (tmp_path / "constant/polyMesh").mkdir(parents=True)
    (tmp_path / "0").mkdir()
    (tmp_path / "constant/polyMesh/boundary").write_text(
        "FoamFile { class polyBoundaryMesh; }\n2\n(\n inlet { type patch; }\n"
        " walls { type wall; }\n)\n"
    )
    (tmp_path / "0/U").write_text(  # real headers/footers broke an earlier comment regex
        '/*--- header ---*\\\n\\*--- end ---*/\nboundaryField\n{\n #includeEtc "x"\n'
        " inlet { type fixedValue; value (1 0 0); }\n}\n// ****** //\n"
    )
    assert validate_case(tmp_path) == ["0/U: no entry for patch 'walls'"]
    (tmp_path / "0/p").write_text('boundaryField\n{\n ".*" { type zeroGradient; }\n}\n')
    assert len(validate_case(tmp_path)) == 1  # regex patch names are skipped
    import shutil

    if shutil.which("git"):
        assert git_snapshot(tmp_path, "t")
        assert (tmp_path / ".gitignore").is_file()


def test_units_and_block_preview() -> None:
    from foamstudio.core.blockmesh_preview import parse_blockmesh
    from foamstudio.core.units import parse_quantity

    assert parse_quantity("36 km/h", "velocity") == 10
    assert parse_quantity("25 mm", "length") == 0.025
    with pytest.raises(ValueError):
        parse_quantity("3 bar", "length")
    pts, hexes = parse_blockmesh(
        "convertToMeters 0.1; // c\nvertices ( (0 0 0) (1 0 0) (1 1 0) (0 1 0)"
        " (0 0 1) (1 0 1) (1 1 1) (0 1 1) );\n"
        "blocks ( hex (0 1 2 3 4 5 6 7) (20 20 1) simpleGrading (1 1 1) );"
    )
    assert pts[6] == (0.1, 0.1, 0.1) and hexes == [(0, 1, 2, 3, 4, 5, 6, 7)]
    with pytest.raises(ValueError):
        parse_blockmesh("vertices ( ($x 0 0) ); blocks ( );")
