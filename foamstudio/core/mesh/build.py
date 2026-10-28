"""blockMesh and snappyHexMesh dictionaries, and a Gmsh subprocess driver.

These are mesh dictionaries. Solver dictionaries stay in openfoam_case_generator.html.
"""

from __future__ import annotations

import math
from pathlib import Path

_FOOTER = "\n// ************************************************************************* //\n"


class MeshFailure(Exception):
    def __init__(self, message: str, suggestion: str) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"{message}\n\n{suggestion}")


def foam_dictionary(object_name: str, body: str) -> str:
    header = (
        "/*--------------------------------*- C++ -*----------------------------------*\\\n"
        "| FoamStudio mesh dictionary                                                 |\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n"
        "{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        "    class       dictionary;\n"
        f"    object      {object_name};\n"
        "}\n"
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n"
    )
    return header + body.rstrip() + _FOOTER


def _num(value: float) -> str:
    return f"{value:.8g}"


def block_mesh_dict(
    kind: str,
    *,
    length: float = 1.0,
    height: float = 1.0,
    width: float = 0.1,
    cells: tuple[int, int, int] = (10, 10, 1),
    angle_deg: float = 5.0,
    radius: float = 1.0,
) -> str:
    """Box, channel, or axisymmetric wedge blockMeshDict."""
    if kind not in {"box", "channel", "wedge"}:
        raise MeshFailure(
            f"Unknown block mesh {kind!r}.",
            suggestion="Use box, channel, or wedge.",
        )
    if min(cells) < 1:
        raise MeshFailure(
            f"Cell counts {cells} must all be at least 1.",
            suggestion="Set nx, ny, and nz to positive integers.",
        )
    if kind == "wedge":
        return foam_dictionary("blockMeshDict", _wedge(length, radius, angle_deg, cells))
    return foam_dictionary("blockMeshDict", _hex(kind, length, height, width, cells))


def _hex(kind: str, length: float, height: float, width: float, cells: tuple[int, int, int]) -> str:
    nx, ny, nz = cells
    z_type = "empty" if nz == 1 else "wall"
    x_min = "patch" if kind == "channel" else "wall"
    x_max = "patch" if kind == "channel" else "wall"
    x_min_name = "inlet" if kind == "channel" else "xMin"
    x_max_name = "outlet" if kind == "channel" else "xMax"
    vertices = "\n".join(
        [
            "    (0 0 0)",
            f"    ({_num(length)} 0 0)",
            f"    ({_num(length)} {_num(height)} 0)",
            f"    (0 {_num(height)} 0)",
            f"    (0 0 {_num(width)})",
            f"    ({_num(length)} 0 {_num(width)})",
            f"    ({_num(length)} {_num(height)} {_num(width)})",
            f"    (0 {_num(height)} {_num(width)})",
        ]
    )
    return (
        "convertToMeters 1;\n\n"
        "vertices\n(\n"
        f"{vertices}\n"
        ");\n\n"
        "blocks\n(\n"
        f"    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)\n"
        ");\n\n"
        "edges\n(\n);\n\n"
        "boundary\n(\n"
        f"{_patch(x_min_name, x_min, '(0 4 7 3)')}\n"
        f"{_patch(x_max_name, x_max, '(1 2 6 5)')}\n"
        f"{_patch('yMin', 'wall', '(0 1 5 4)')}\n"
        f"{_patch('yMax', 'wall', '(3 7 6 2)')}\n"
        f"{_patch('zMin', z_type, '(0 3 2 1)')}\n"
        f"{_patch('zMax', z_type, '(4 5 6 7)')}\n"
        ");\n\n"
        "mergePatchPairs\n(\n);\n"
    )


def _wedge(length: float, radius: float, angle_deg: float, cells: tuple[int, int, int]) -> str:
    if angle_deg <= 0 or angle_deg >= 90:
        raise MeshFailure(
            f"Wedge angle {angle_deg} degrees is outside (0, 90).",
            suggestion="Use a small angle such as 5 degrees. The two wedge faces must not be flat.",
        )
    half = math.radians(angle_deg) / 2.0
    sine = math.sin(half)
    cosine = math.cos(half)
    nx, nr, _nz = cells
    y = radius * sine
    z = radius * cosine
    # The axis vertices are repeated. OpenFOAM accepts that for a wedge from r = 0.
    vertices = "\n".join(
        [
            "    (0 0 0)",
            f"    ({_num(length)} 0 0)",
            f"    ({_num(length)} {_num(y)} {_num(z)})",
            f"    (0 {_num(y)} {_num(z)})",
            "    (0 0 0)",
            f"    ({_num(length)} 0 0)",
            f"    ({_num(length)} {_num(-y)} {_num(z)})",
            f"    (0 {_num(-y)} {_num(z)})",
        ]
    )
    return (
        "convertToMeters 1;\n\n"
        "vertices\n(\n"
        f"{vertices}\n"
        ");\n\n"
        "blocks\n(\n"
        f"    hex (0 1 2 3 4 5 6 7) ({nx} {nr} 1) simpleGrading (1 1 1)\n"
        ");\n\n"
        "edges\n(\n);\n\n"
        "boundary\n(\n"
        f"{_patch('inlet', 'patch', '(0 4 7 3)')}\n"
        f"{_patch('outlet', 'patch', '(1 2 6 5)')}\n"
        f"{_patch('walls', 'wall', '(3 7 6 2)')}\n"
        f"{_patch('axis', 'empty', '(0 1 5 4)')}\n"
        f"{_patch('wedgeFront', 'wedge', '(0 3 2 1)')}\n"
        f"{_patch('wedgeBack', 'wedge', '(4 5 6 7)')}\n"
        ");\n\n"
        "mergePatchPairs\n(\n);\n"
    )


def _patch(name: str, kind: str, face: str) -> str:
    return (
        f"    {name}\n"
        "    {\n"
        f"        type {kind};\n"
        "        faces\n"
        "        (\n"
        f"            {face}\n"
        "        );\n"
        "    }"
    )


def first_cell_height(velocity: float, nu: float, length: float, y_plus: float) -> float:
    """Flat-plate estimate. cf = 0.058 Re^{-0.2}, then y = y+ * nu / u_tau."""
    if velocity <= 0 or nu <= 0 or length <= 0 or y_plus <= 0:
        raise MeshFailure(
            "y+ inputs must be positive (velocity, nu, length, y+).",
            suggestion="Set a freestream speed, kinematic viscosity, plate length, and target y+.",
        )
    reynolds = velocity * length / nu
    cf = 0.058 * reynolds ** (-0.2)
    u_tau = velocity * math.sqrt(cf / 2.0)
    return y_plus * nu / u_tau


def yplus_matches(estimate: float, measured: float, *, tolerance: float = 0.2) -> bool:
    if estimate <= 0:
        raise MeshFailure(
            "The y+ estimate must be positive before it is compared.",
            suggestion="Compute first_cell_height before reading the yPlus log.",
        )
    return abs(measured - estimate) <= tolerance * abs(estimate)


def snappy_hex_mesh_dict(
    stl_name: str,
    *,
    regions: tuple[tuple[str, int], ...] = (),
    velocity: float = 1.0,
    nu: float = 1e-5,
    length: float = 1.0,
    y_plus: float = 30.0,
    n_surface: int = 2,
    layers: int = 3,
    location: tuple[float, float, float] = (0.5, 0.5, 0.05),
) -> str:
    height = first_cell_height(velocity, nu, length, y_plus)
    region_body = "\n".join(
        f"        {name}\n"
        "        {\n"
        "            mode inside;\n"
        f"            levels ((1E15 {level}));\n"
        "        }"
        for name, level in regions
    )
    if not region_body:
        region_body = "        // no extra refinement regions"
    body = (
        "castellatedMesh true;\n"
        "snap            true;\n"
        "addLayers       true;\n\n"
        "geometry\n{\n"
        f"    {stl_name}\n    {{\n        type triSurfaceMesh;\n        name {stl_name};\n    }}\n"
        "}\n\n"
        "castellatedMeshControls\n{\n"
        "    maxLocalCells 1000000;\n"
        "    maxGlobalCells 2000000;\n"
        "    minRefinementCells 0;\n"
        "    nCellsBetweenLevels 2;\n"
        "    refinementSurfaces\n    {\n"
        f"        {stl_name}\n"
        "        {\n"
        f"            level ({n_surface} {n_surface});\n"
        "        }\n"
        "    }\n"
        "    refinementRegions\n    {\n"
        f"{region_body}\n"
        "    }\n"
        f"    locationInMesh ({_num(location[0])} {_num(location[1])} {_num(location[2])});\n"
        "    allowFreeStandingZoneFaces true;\n"
        "}\n\n"
        "snapControls\n{\n"
        "    nSmoothPatch 3;\n"
        "    tolerance 2.0;\n"
        "    nSolveIter 30;\n"
        "    nRelaxIter 5;\n"
        "}\n\n"
        "addLayersControls\n{\n"
        "    relativeSizes false;\n"
        "    layers\n    {\n"
        f"        {stl_name}\n        {{\n            nSurfaceLayers {layers};\n        }}\n"
        "    }\n"
        "    expansionRatio 1.2;\n"
        f"    firstLayerThickness {height:.8g};\n"
        "    minThickness 1e-6;\n"
        "    nGrow 0;\n"
        "    featureAngle 60;\n"
        "    nRelaxIter 3;\n"
        "    nSmoothSurfaceNormals 1;\n"
        "    nSmoothNormals 3;\n"
        "    nSmoothThickness 10;\n"
        "    maxFaceThicknessRatio 0.5;\n"
        "    maxThicknessToMedialRatio 0.3;\n"
        "    minMedialAxisAngle 90;\n"
        "    nBufferCellsNoExtrude 0;\n"
        "    nLayerIter 50;\n"
        "}\n\n"
        "meshQualityControls\n{\n"
        "    maxNonOrtho 65;\n"
        "    maxBoundarySkewness 20;\n"
        "    maxInternalSkewness 4;\n"
        "    maxConcave 80;\n"
        "    minVol 1e-13;\n"
        "    minTetQuality -1e30;\n"
        "    minArea -1;\n"
        "    minTwist 0.02;\n"
        "    minDeterminant 0.001;\n"
        "    minFaceWeight 0.05;\n"
        "    minVolRatio 0.01;\n"
        "    minTriangleTwist -1;\n"
        "    nSmoothScale 4;\n"
        "    errorReduction 0.75;\n"
        "}\n\n"
        "mergeTolerance 1e-6;\n"
    )
    return foam_dictionary("snappyHexMeshDict", body)


def gmsh_geo(geometry: Path, *, size: float = 0.1) -> str:
    quoted = str(geometry).replace("\\", "/")
    return (
        f'SetFactory("OpenCASCADE");\n'
        f'Merge "{quoted}";\n'
        f"Mesh.CharacteristicLengthMax = {_num(size)};\n"
        "Mesh 3;\n"
    )


def gmsh_argv(geometry: Path, output: Path) -> tuple[str, ...]:
    return ("gmsh", "-3", "-format", "msh2", str(geometry), "-o", str(output))


def write_gmsh_driver(geometry: Path, output: Path, *, size: float = 0.1) -> tuple[str, ...]:
    """Write a .geo next to the output and return the gmsh command. Does not run it."""
    if "$" in str(geometry) or "$" in str(output):
        raise MeshFailure(
            "The Gmsh path contains '$'.",
            suggestion="Rename the folder so the path has no dollar sign, then generate the mesh.",
        )
    script = output.with_suffix(".geo")
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(gmsh_geo(geometry, size=size), encoding="utf-8", newline="\n")
    return gmsh_argv(script, output)
