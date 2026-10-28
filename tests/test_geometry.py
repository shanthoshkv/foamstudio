"""Geometry import. Files stay well under 1 MB. Gmsh is not linked."""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path

import pytest

from foamstudio.core.geometry import ImportFailure, generator_patches, guess_role, import_path
from foamstudio.core.geometry.io import read_step
from foamstudio.core.geometry.quality import colour_ramp, colour_values

_ASCII = """solid inlet
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0 1 0
    endloop
  endfacet
endsolid inlet
solid wall
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 0 1 0
      vertex 0 0 1
    endloop
  endfacet
endsolid wall
"""

_GMSH2 = """$MeshFormat
2.2 0 8
$EndMeshFormat
$PhysicalNames
1
2 1 "inlet"
$EndPhysicalNames
$Nodes
3
1 0 0 0
2 1 0 0
3 0 1 0
$EndNodes
$Elements
1
1 2 2 1 1 1 2 3
$EndElements
"""

_GMSH4 = """$MeshFormat
4.1 0 8
$EndMeshFormat
$PhysicalNames
1
2 1 "outlet"
$EndPhysicalNames
$Nodes
1 3 1 3
2 1 0 3
1
2
3
0 0 0
1 0 0
0 1 0
$EndNodes
$Elements
1 1 1 1
2 1 2 1
1 1 2 3
$EndElements
"""

_OBJ = """v 0 0 0
v 1 0 0
v 0 1 0
g inlet
f 1 2 3
"""


def test_ascii_stl_groups_and_roles(tmp_path: Path) -> None:
    path = tmp_path / "box.stl"
    path.write_text(_ASCII, encoding="utf-8")
    surface = import_path(path)
    assert len(surface.triangles) == 2
    assert [patch.name for patch in surface.patches] == ["inlet", "wall"]
    assert surface.patch("inlet").role == "inlet"
    assert surface.patch("wall").role == "wall"
    rows = generator_patches(surface, "wall")
    assert rows[0] == {"name": "wall", "role": "wall"}
    with pytest.raises(ImportFailure, match="not on"):
        generator_patches(surface, "nope")


def test_binary_stl_one_triangle(tmp_path: Path) -> None:
    path = tmp_path / "one.stl"
    header = b"foamstudio".ljust(80, b"\0")
    triangle = struct.pack("<12fH", 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)
    path.write_bytes(header + struct.pack("<I", 1) + triangle)
    surface = import_path(path)
    assert len(surface.triangles) == 1
    assert surface.patches[0].name == "one"


def test_obj_group_and_bad_index(tmp_path: Path) -> None:
    path = tmp_path / "tri.obj"
    path.write_text(_OBJ, encoding="utf-8")
    surface = import_path(path)
    assert surface.patches[0].name == "inlet"
    assert surface.patches[0].role == "inlet"
    broken = tmp_path / "bad.obj"
    broken.write_text("v 0 0 0\nf 1 2 9\n", encoding="utf-8")
    with pytest.raises(ImportFailure, match="outside"):
        import_path(broken)


def test_gmsh_22_and_41(tmp_path: Path) -> None:
    old = tmp_path / "old.msh"
    old.write_text(_GMSH2, encoding="utf-8")
    surface = import_path(old)
    assert surface.patches[0].name == "inlet"
    assert len(surface.triangles) == 1
    new = tmp_path / "new.msh"
    new.write_text(_GMSH4, encoding="utf-8")
    newer = import_path(new)
    assert newer.patches[0].name == "outlet"
    assert newer.patches[0].role == "outlet"


def test_openfoam_boundary(tmp_path: Path) -> None:
    mesh = tmp_path / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    (mesh / "boundary").write_text(
        "2\n(\ninlet\n{\n type patch;\n nFaces 1;\n startFace 0;\n}\n"
        "walls\n{\n type wall;\n nFaces 0;\n startFace 1;\n}\n)\n",
        encoding="utf-8",
    )
    (mesh / "points").write_text("(0 0 0)\n(1 0 0)\n(0 1 0)\n", encoding="utf-8")
    (mesh / "faces").write_text("3(0 1 2)\n", encoding="utf-8")
    surface = import_path(tmp_path)
    assert surface.patch("inlet").role == "inlet"
    assert surface.patch("walls").role == "wall"
    assert len(surface.triangles) == 1


def test_step_is_a_gmsh_subprocess(tmp_path: Path) -> None:
    step = tmp_path / "part.step"
    step.write_text("ISO-10303-21;", encoding="utf-8")

    def fake(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(argv[-1]).write_text(_GMSH2, encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    surface = read_step(step, run=fake)
    assert surface.patches[0].name == "inlet"

    def missing(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(argv[0])

    with pytest.raises(ImportFailure, match="127"):
        read_step(step, run=missing)


def test_fluent_meshio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Block:
        type = "triangle"
        data = [[0, 1, 2]]

    class _Mesh:
        points = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        cells = [_Block()]
        cell_sets = {"inlet": object()}

    monkeypatch.setattr("meshio.read", lambda _path: _Mesh())
    path = tmp_path / "fluent.msh"
    path.write_text('(0 "fluent")\n', encoding="utf-8")
    surface = import_path(path)
    assert surface.patches[0].name == "inlet"
    assert len(surface.triangles) == 1


def test_import_failures_name_a_fix(tmp_path: Path) -> None:
    missing = tmp_path / "missing.stl"
    with pytest.raises(ImportFailure, match="not a file"):
        import_path(missing)
    empty = tmp_path / "empty.stl"
    empty.write_bytes(b" \n")
    with pytest.raises(ImportFailure, match="empty"):
        import_path(empty)
    other = tmp_path / "part.iges"
    other.write_text("x", encoding="utf-8")
    with pytest.raises(ImportFailure, match="Unsupported"):
        import_path(other)
    assert guess_role("symPlane") == "symmetry"
    assert guess_role("front", "empty") == "empty"


def test_colour_ramp_ends() -> None:
    assert colour_ramp(0, 0, 1) == (68, 1, 84)
    assert colour_ramp(1, 0, 1) == (253, 231, 37)
    colours = colour_values([1.0, 2.0])
    assert colours[0] == (68, 1, 84)
    assert colours[1] == (253, 231, 37)
    assert colour_values([]) == []
