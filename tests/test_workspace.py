from __future__ import annotations

from pathlib import Path

import pytest

from foamstudio.core import workspace as ws


def _case(root: Path) -> Path:
    for part in ("0", "constant", "system"):
        (root / part).mkdir(parents=True)
    (root / "system" / "controlDict").write_bytes(b"application simpleFoam;\r\n")
    (root / "0" / "U").write_text("internalField uniform (0 0 0);\n", encoding="utf-8")
    (root / "Allrun").write_bytes(b"#!/bin/sh\r\necho hi\r\n")
    return root


def test_import_whole_case_and_single_parts(tmp_path: Path) -> None:
    src = _case(tmp_path / "src")
    dest = tmp_path / "dest" / "case"
    kind, files = ws.import_into(src, dest)
    assert kind == "case" and len(files) == 3
    assert (dest / "system" / "controlDict").read_bytes() == b"application simpleFoam;\n"
    assert b"\r" not in (dest / "Allrun").read_bytes()
    one = tmp_path / "one" / "case"
    assert ws.import_into(src / "0", one)[0] == "part" and (one / "0" / "U").is_file()
    assert (
        ws.import_into(src / "system", one)[0] == "part" and (one / "system/controlDict").is_file()
    )
    holder = tmp_path / "holder"
    (holder / "constant").mkdir(parents=True)
    (holder / "constant" / "transportProperties").write_text("nu 1e-5;\n", encoding="utf-8")
    assert ws.import_into(holder, one)[0] == "part"
    assert (one / "constant" / "transportProperties").is_file()


def test_import_geometry_mesh_scripts(tmp_path: Path) -> None:
    geo = tmp_path / "geo"
    geo.mkdir()
    (geo / "body.stl").write_text("solid a\nendsolid a\n", encoding="utf-8")
    case = tmp_path / "case"
    assert ws.import_into(geo, case)[0] == "geometry"
    assert (case / "constant" / "triSurface" / "body.stl").is_file()
    scripts = tmp_path / "s"
    scripts.mkdir()
    (scripts / "post.py").write_text("print(1)\n", encoding="utf-8")
    (scripts / "Allrun.pre").write_text("blockMesh\n", encoding="utf-8")
    assert ws.import_into(scripts, case)[0] == "scripts"
    assert [p.name for p in ws.scripts_in(case)] == ["Allrun.pre", "post.py"]
    assert ws.script_command(case / "post.py") == "python3 ./post.py"
    assert ws.script_command(case / "Allrun.pre") == "bash ./Allrun.pre"
    with pytest.raises(ValueError):
        ws.script_command(case / "a b;rm.sh")
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "x.msh").write_bytes(b"\0mesh")
    assert ws.classify(tmp_path / "m") == "mesh"


def test_wslconfig_roundtrip(tmp_path: Path) -> None:
    cfg = tmp_path / ".wslconfig"
    cfg.write_text(
        "[wsl2]\nmemory=4GB\nnetworkingMode=mirrored\n[experimental]\nx=1\n", encoding="ascii"
    )
    ws.write_wslconfig(2, 1, 0, cfg)
    text = cfg.read_text(encoding="ascii")
    assert "memory=2GB" in text and "networkingMode=mirrored" in text and "[experimental]" in text
    assert ws.read_wslconfig(cfg)["memory"] == "2GB"
    with pytest.raises(ValueError):
        ws.write_wslconfig(10_000, 1, 0, cfg)
    assert str(ws.wsl_unc("Ubuntu", "/home/u/c")).endswith(r"Ubuntu\home\u\c")


def test_boundary_checks_history_disk_compare(tmp_path: Path) -> None:
    case = _case(tmp_path / "p" / "case")
    poly = case / "constant" / "polyMesh"
    poly.mkdir()
    (poly / "boundary").write_text(
        "2\n(\n    inlet\n    {\n        type patch;\n        nFaces 4;\n"
        "        startFace 0;\n    }\n"
        "    side\n    {\n        type wall;\n        inGroups 1(wall);\n        nFaces 8;\n"
        "        startFace 4;\n    }\n)\n",
        encoding="utf-8",
    )
    assert ws.boundary_patches(case) == [("inlet", "patch", 4), ("side", "wall", 8)]
    ws.edit_boundary(case, "side", new_name="top", new_type="symmetryPlane")
    assert ws.boundary_patches(case)[1] == ("top", "symmetryPlane", 8)
    assert "inGroups" not in (poly / "boundary").read_text(encoding="utf-8")
    rows = ws.check_table(
        "cells:            100\n    Mesh non-orthogonality Max: 75.2 average: 3\n"
        "    Max skewness = 0.5 OK.\nFailed 1 mesh checks.\n"
    )
    assert [r.ok for r in rows] == [True, False, True, False]
    ws.record_run(case, "simpleFoam", "succeeded", 0.0, 12.5)
    assert ws.load_history(case)[0]["seconds"] == 12.5
    for t in ("0.5", "1"):
        (case / t).mkdir()
    (case / "processor0").mkdir()
    assert len(ws.clean(case, processors=True, keep_latest=True)) == 2
    assert (case / "1").is_dir() and not (case / "0.5").exists()
    other = _case(tmp_path / "q")
    (other / "0" / "U").write_text("internalField uniform (1 0 0);\n", encoding="utf-8")
    assert "+internalField uniform (1 0 0);" in ws.compare_cases(case, other)
    out = ws.export_csv({"Time": [1.0, 2.0], "Cd": [0.1, 0.2]}, tmp_path / "c.csv")
    assert out.read_text(encoding="utf-8").splitlines()[1] == "1.0,0.1"
    log = "Courant Number mean: 0.1 max: 0.9\ndeltaT = 0.001\nTime = 1\n"
    assert ws.monitor(log) == {"Courant mean": 0.1, "Courant max": 0.9, "deltaT": 0.001}
    assert "cavity/case" in ws.templates()


def test_dictionary_checks() -> None:
    pytest.importorskip("PySide6")
    from foamstudio.ui.dict_editor import check_dictionary

    assert check_dictionary("a 1;\nb\n{\n    c 2;\n}\n") == []
    problems = check_dictionary("a 1\nb {\n")
    assert any("missing ';'" in p for p in problems) and any("Unbalanced" in p for p in problems)


def test_block_vertices(tmp_path: Path) -> None:
    from foamstudio.core.mesh import block_mesh_dict

    (tmp_path / "system").mkdir()
    mesh = tmp_path / "system" / "blockMeshDict"
    mesh.write_text(block_mesh_dict("box", length=1, height=1, width=0.1, cells=(4, 4, 1)))
    points = ws.block_vertices(tmp_path)
    assert len(points) == 8 and points[6] == (1.0, 1.0, 0.1)
    ws.set_block_vertices(tmp_path, [(x * 2, y, z) for x, y, z in points])
    assert ws.block_vertices(tmp_path)[6] == (2.0, 1.0, 0.1)
    assert "blocks" in mesh.read_text()
    with pytest.raises(ValueError):
        ws.set_block_vertices(tmp_path, points[:4])
