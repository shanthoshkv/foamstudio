"""STL, OBJ, Gmsh, Fluent, STEP, and OpenFOAM boundary readers."""

from __future__ import annotations

import struct
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from foamstudio.core.geometry.model import ImportFailure, Patch, Surface, Triangle, guess_role

Point = tuple[float, float, float]
_Completed = subprocess.CompletedProcess[str]


def read_path(path: Path) -> Surface:
    if path.is_dir():
        return read_openfoam(path)
    if not path.is_file():
        raise ImportFailure(
            f"{path} is not a file or an OpenFOAM case directory.",
            suggestion="Choose an STL, OBJ, MSH, STEP file, or a case with constant/polyMesh.",
        )
    suffix = path.suffix.lower()
    data = path.read_bytes()
    if suffix == ".stl":
        return read_stl(path, data)
    if suffix == ".obj":
        return read_obj(path, data.decode("utf-8", errors="replace"))
    if suffix in {".step", ".stp"}:
        return read_step(path)
    if suffix == ".msh":
        text = data.decode("utf-8", errors="replace")
        if "$MeshFormat" in text:
            return read_gmsh(path, text)
        return read_fluent(path)
    raise ImportFailure(
        f"Unsupported geometry type {suffix or '(none)'} ({path.name}).",
        suggestion="Use .stl, .obj, .msh (Gmsh or Fluent), .step, or an OpenFOAM case directory.",
    )


def _surface(
    name: str,
    source: str,
    triangles: Sequence[Triangle],
    groups: Sequence[tuple[str, str, Sequence[int]]],
    zones: Sequence[str] = (),
) -> Surface:
    if not groups:
        raise ImportFailure(
            f"{name} did not contain a patch.",
            suggestion=(
                "Export the file with named solids, groups, physical groups, or boundary patches."
            ),
        )
    patches = tuple(Patch(patch_name, role, tuple(indexes)) for patch_name, role, indexes in groups)
    return Surface(name, source, tuple(triangles), patches, tuple(zones))


def read_stl(path: Path, data: bytes) -> Surface:
    if not data.strip():
        raise ImportFailure(
            f"{path.name} is empty.",
            suggestion="Export the STL again from the CAD tool.",
        )
    if _binary_stl(data):
        triangles = _binary_triangles(path, data)
        groups = [(path.stem or "solid", "wall", range(len(triangles)))]
        return _surface(path.stem, str(path), triangles, groups)
    return _ascii_stl(path, data.decode("utf-8", errors="replace"))


def _binary_stl(data: bytes) -> bool:
    if len(data) < 84:
        return False
    count = int.from_bytes(data[80:84], "little")
    if count >= 0 and 84 + count * 50 == len(data):
        return True
    return b"facet" not in data[:4096].lower()


def _binary_triangles(path: Path, data: bytes) -> list[Triangle]:
    count = int.from_bytes(data[80:84], "little")
    expected = 84 + count * 50
    if expected != len(data):
        raise ImportFailure(
            f"{path.name} is not a binary STL of {count} triangles ({len(data)} bytes).",
            suggestion="Re-export the STL as ASCII or as a standard binary STL.",
        )
    triangles: list[Triangle] = []
    offset = 84
    for _ in range(count):
        numbers = struct.unpack_from("<12fH", data, offset)
        offset += 50
        triangles.append(
            Triangle(
                (numbers[3], numbers[4], numbers[5]),
                (numbers[6], numbers[7], numbers[8]),
                (numbers[9], numbers[10], numbers[11]),
            )
        )
    if not triangles:
        raise ImportFailure(
            f"{path.name} has no triangles.",
            suggestion="Export a closed surface, not an empty STL.",
        )
    return triangles


def _ascii_stl(path: Path, text: str) -> Surface:
    triangles: list[Triangle] = []
    groups: list[tuple[str, str, list[int]]] = []
    name = path.stem or "solid"
    current: list[int] = []
    verts: list[Point] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower().startswith("solid"):
            if current:
                groups.append((name, guess_role(name), current))
            token = line.split(maxsplit=1)
            name = token[1].strip() if len(token) == 2 and token[1].strip() else path.stem
            current = []
            continue
        if line.lower().startswith("vertex"):
            parts = line.split()
            if len(parts) < 4:
                raise ImportFailure(
                    f"{path.name} has a vertex line that is not three numbers.",
                    suggestion="Re-export the ASCII STL.",
                )
            current_vertex = (float(parts[1]), float(parts[2]), float(parts[3]))
            verts.append(current_vertex)
            if len(verts) == 3:
                triangles.append(Triangle(verts[0], verts[1], verts[2]))
                current.append(len(triangles) - 1)
                verts = []
        if line.lower().startswith("endsolid") and current:
            groups.append((name, guess_role(name), list(current)))
            current = []
    if current:
        groups.append((name, guess_role(name), current))
    if not triangles:
        raise ImportFailure(
            f"{path.name} has no ASCII facets.",
            suggestion="Re-export the STL. A binary STL must be 84 + 50*N bytes.",
        )
    packed = [(item[0], item[1], item[2]) for item in groups]
    return _surface(path.stem, str(path), triangles, packed, tuple(item[0] for item in groups))


def read_obj(path: Path, text: str) -> Surface:
    points: list[Point] = []
    triangles: list[Triangle] = []
    groups: list[tuple[str, list[int]]] = []
    name = "default"
    bucket: list[int] = []

    def flush() -> None:
        nonlocal bucket
        if bucket:
            groups.append((name, bucket))
            bucket = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("v "):
            parts = line.split()
            if len(parts) < 4:
                raise ImportFailure(
                    f"{path.name} has a vertex that is not three numbers.",
                    suggestion="Re-export the OBJ with v x y z lines.",
                )
            points.append((float(parts[1]), float(parts[2]), float(parts[3])))
            continue
        if line.startswith("g ") or line.startswith("o "):
            flush()
            name = line.split(maxsplit=1)[1].strip() or "default"
            continue
        if line.startswith("f "):
            indexes = [_obj_index(token, len(points), path.name) for token in line.split()[1:]]
            if len(indexes) < 3:
                continue
            for second, third in zip(indexes[1:], indexes[2:], strict=False):
                triangles.append(Triangle(points[indexes[0]], points[second], points[third]))
                bucket.append(len(triangles) - 1)
    flush()
    if not triangles:
        raise ImportFailure(
            f"{path.name} has no faces.",
            suggestion="Export the OBJ with f lines that refer to v vertices.",
        )
    packed = [(group, guess_role(group), indexes) for group, indexes in groups]
    return _surface(path.stem, str(path), triangles, packed, tuple(item[0] for item in groups))


def _obj_index(token: str, count: int, filename: str) -> int:
    piece = token.split("/")[0]
    if not piece:
        raise ImportFailure(
            f"{filename} has a face index that is blank.",
            suggestion="Export faces as f v1 v2 v3.",
        )
    number = int(piece)
    index = number - 1 if number > 0 else count + number
    if index < 0 or index >= count:
        raise ImportFailure(
            f"{filename} face index {token} is outside 1..{count}.",
            suggestion="Export the OBJ again. FoamStudio does not read free-form curves.",
        )
    return index


def read_gmsh(path: Path, text: str) -> Surface:
    version = _mesh_version(text)
    if version.startswith("2."):
        return _gmsh2(path, text)
    if version.startswith("4."):
        return _gmsh4(path, text)
    raise ImportFailure(
        f"{path.name} is Gmsh {version or 'unknown'}, which FoamStudio does not read.",
        suggestion="Export msh 2.2 or 4.1 ASCII: gmsh -format msh2 file.geo",
    )


def _mesh_version(text: str) -> str:
    body = _section(text, "MeshFormat")
    if body is None:
        return ""
    line = next((item.strip() for item in body.splitlines() if item.strip()), "")
    return line.split()[0] if line else ""


def _section(text: str, name: str) -> str | None:
    marker = f"${name}"
    start = text.find(marker)
    if start < 0:
        return None
    newline = text.find("\n", start)
    end = text.find(f"$End{name}", start)
    if newline < 0 or end < 0:
        return None
    return text[newline + 1 : end]


def _physical_names(text: str) -> dict[int, str]:
    body = _section(text, "PhysicalNames")
    names: dict[int, str] = {}
    if body is None:
        return names
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.isdigit():
            continue
        parts = stripped.split(maxsplit=2)
        if len(parts) < 3:
            continue
        names[int(parts[1])] = parts[2].strip().strip('"')
    return names


def _gmsh2(path: Path, text: str) -> Surface:
    nodes = _gmsh2_nodes(path, _section(text, "Nodes") or "")
    names = _physical_names(text)
    body = _section(text, "Elements")
    if body is None:
        raise ImportFailure(
            f"{path.name} has no $Elements block.",
            suggestion="Export a surface mesh (gmsh -2) or a volume mesh with boundary elements.",
        )
    triangles: list[Triangle] = []
    buckets: dict[str, list[int]] = {}
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    entries = lines[1:] if lines and lines[0].isdigit() else lines
    for line in entries:
        parts = line.split()
        if len(parts) < 4:
            continue
        element_type = int(parts[1])
        tag_count = int(parts[2])
        tags = [int(part) for part in parts[3 : 3 + tag_count]]
        nodes_on_element = [int(part) for part in parts[3 + tag_count :]]
        physical = tags[0] if tags else 0
        label = names.get(physical, "surface")
        for tri in _fan(element_type, nodes_on_element):
            triangles.append(_tri(nodes, tri, path.name))
            buckets.setdefault(label, []).append(len(triangles) - 1)
    return _from_buckets(path, triangles, buckets)


def _gmsh2_nodes(path: Path, body: str) -> dict[int, Point]:
    nodes: dict[int, Point] = {}
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    entries = lines[1:] if lines and lines[0].isdigit() else lines
    for line in entries:
        parts = line.split()
        if len(parts) < 4:
            continue
        nodes[int(parts[0])] = (float(parts[1]), float(parts[2]), float(parts[3]))
    if not nodes:
        raise ImportFailure(
            f"{path.name} has no Gmsh nodes.",
            suggestion="Export ASCII msh 2.2 with a $Nodes block.",
        )
    return nodes


def _gmsh4(path: Path, text: str) -> Surface:
    names = _physical_names(text)
    nodes = _gmsh4_nodes(path, _section(text, "Nodes") or "")
    body = _section(text, "Elements")
    if body is None:
        raise ImportFailure(
            f"{path.name} has no $Elements block.",
            suggestion="Export msh 4.1 ASCII, or msh 2.2.",
        )
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        raise ImportFailure(
            f"{path.name} has an empty $Elements block.",
            suggestion="Export a mesh that contains triangles.",
        )
    cursor = 1 if len(lines[0].split()) >= 4 else 0
    triangles: list[Triangle] = []
    buckets: dict[str, list[int]] = {}
    while cursor < len(lines):
        header = lines[cursor].split()
        if len(header) < 4:
            cursor += 1
            continue
        entity_tag = int(header[1])
        element_type = int(header[2])
        count = int(header[3])
        label = names.get(entity_tag, names.get(entity_tag, "surface"))
        cursor += 1
        for _ in range(count):
            if cursor >= len(lines):
                break
            parts = [int(part) for part in lines[cursor].split()]
            cursor += 1
            nodes_on_element = parts[1:]
            for tri in _fan(element_type, nodes_on_element):
                triangles.append(_tri(nodes, tri, path.name))
                buckets.setdefault(label, []).append(len(triangles) - 1)
    return _from_buckets(path, triangles, buckets)


def _gmsh4_nodes(path: Path, body: str) -> dict[int, Point]:
    nodes: dict[int, Point] = {}
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        raise ImportFailure(
            f"{path.name} has no Gmsh 4 nodes.",
            suggestion="Export ASCII msh 4.1 with a $Nodes block.",
        )
    cursor = 1
    while cursor < len(lines):
        header = lines[cursor].split()
        if len(header) < 4:
            cursor += 1
            continue
        count = int(header[3])
        cursor += 1
        tags = []
        for _ in range(count):
            tags.append(int(lines[cursor].split()[0]))
            cursor += 1
        for tag in tags:
            coords = lines[cursor].split()
            cursor += 1
            nodes[tag] = (float(coords[0]), float(coords[1]), float(coords[2]))
    if not nodes:
        raise ImportFailure(
            f"{path.name} has no Gmsh 4 node coordinates.",
            suggestion="Export ASCII msh 4.1, or msh 2.2.",
        )
    return nodes


def _fan(element_type: int, nodes: list[int]) -> list[tuple[int, int, int]]:
    if element_type == 2 and len(nodes) >= 3:
        return [(nodes[0], nodes[1], nodes[2])]
    if element_type == 3 and len(nodes) >= 4:
        return [(nodes[0], nodes[1], nodes[2]), (nodes[0], nodes[2], nodes[3])]
    return []


def _tri(nodes: dict[int, Point], indexes: tuple[int, int, int], filename: str) -> Triangle:
    try:
        return Triangle(nodes[indexes[0]], nodes[indexes[1]], nodes[indexes[2]])
    except KeyError as exc:
        raise ImportFailure(
            f"{filename} element refers to missing node {exc}.",
            suggestion="Export the mesh again so node tags match the elements.",
        ) from exc


def _from_buckets(path: Path, triangles: list[Triangle], buckets: dict[str, list[int]]) -> Surface:
    if not triangles or not buckets:
        raise ImportFailure(
            f"{path.name} has no triangle elements.",
            suggestion="Export triangles (Gmsh element type 2) or quads (type 3).",
        )
    packed = [(name, guess_role(name), indexes) for name, indexes in buckets.items()]
    return _surface(path.stem, str(path), triangles, packed, tuple(buckets))


def read_fluent(path: Path) -> Surface:
    try:
        import meshio
    except ImportError as exc:
        raise ImportFailure(
            "meshio is not installed, so this Fluent mesh cannot be read.",
            suggestion='Install FoamStudio with its geometry extras: pip install -e ".[dev]".',
        ) from exc
    try:
        mesh = meshio.read(path)
    except Exception as exc:
        raise ImportFailure(
            f"meshio could not read {path.name}: {exc}",
            suggestion=f"Convert it with: meshio convert {path} case.msh",
        ) from exc
    triangles = _meshio_triangles(mesh, path.name)
    groups = _meshio_groups(mesh, len(triangles))
    return _surface(path.stem, str(path), triangles, groups)


def _meshio_triangles(mesh: Any, filename: str) -> list[Triangle]:
    points = mesh.points
    triangles: list[Triangle] = []
    for block in mesh.cells:
        kind = str(block.type)
        if kind not in {"triangle", "quad"}:
            continue
        for cell in block.data:
            indexes = [int(item) for item in cell]
            fans = [indexes[:3]]
            if kind == "quad" and len(indexes) >= 4:
                fans = [indexes[:3], [indexes[0], indexes[2], indexes[3]]]
            for fan in fans:
                triangles.append(
                    Triangle(
                        _xyz(points[fan[0]]),
                        _xyz(points[fan[1]]),
                        _xyz(points[fan[2]]),
                    )
                )
    if not triangles:
        raise ImportFailure(
            f"meshio read {filename} but it has no triangles.",
            suggestion="Export the Fluent mesh with boundary faces, or convert it to STL.",
        )
    return triangles


def _xyz(point: Sequence[float]) -> Point:
    return (float(point[0]), float(point[1]), float(point[2]))


def _meshio_groups(mesh: Any, count: int) -> list[tuple[str, str, Sequence[int]]]:
    sets = getattr(mesh, "cell_sets", None)
    groups: list[tuple[str, str, Sequence[int]]] = []
    if isinstance(sets, dict):
        mapping = cast(dict[object, object], sets)
        for key, _value in mapping.items():
            label = str(key)
            if label.startswith("gmsh:"):
                continue
            groups.append((label, guess_role(label), range(count)))
    if not groups:
        groups.append(("fluent", "wall", range(count)))
    return groups


def step_argv(source: Path, output: Path) -> tuple[str, ...]:
    """Gmsh stays a separate process. FoamStudio does not link it."""
    return ("gmsh", "-3", "-format", "msh2", str(source), "-o", str(output))


def read_step(
    path: Path,
    *,
    run: Callable[..., _Completed] | None = None,
) -> Surface:
    output = path.with_name(path.stem + "-foamstudio.msh")
    argv = step_argv(path, output)
    command = " ".join(argv)
    launcher = subprocess.run if run is None else run
    try:
        completed = launcher(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise ImportFailure(
            f"Command failed (127).\n{command}",
            suggestion=(
                "Install Gmsh and retry. FoamStudio runs the gmsh executable. "
                "It does not link the Gmsh library."
            ),
        ) from exc
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "(no output)").strip()
        raise ImportFailure(
            f"Command failed ({completed.returncode}).\n{command}\n\n{tail or '(no output)'}",
            suggestion="Install Gmsh and confirm the STEP file opens in it.",
        )
    if not output.is_file():
        raise ImportFailure(
            f"gmsh exited 0 but did not write {output.name}.\n{command}",
            suggestion="Run the command above in a terminal and read the Gmsh log.",
        )
    return read_gmsh(output, output.read_text(encoding="utf-8", errors="replace"))


def read_openfoam(path: Path) -> Surface:
    boundary = path / "constant" / "polyMesh" / "boundary"
    if not boundary.is_file():
        raise ImportFailure(
            f"No constant/polyMesh/boundary in {path}.",
            suggestion="Choose an OpenFOAM case directory, or import an STL, OBJ, or MSH file.",
        )
    text = boundary.read_text(encoding="utf-8", errors="replace")
    patches = _boundary_patches(text, path)
    points = _points(path / "constant" / "polyMesh" / "points")
    faces = _faces(path / "constant" / "polyMesh" / "faces")
    triangles: list[Triangle] = []
    groups: list[tuple[str, str, list[int]]] = []
    for name, role, count, start in patches:
        indexes: list[int] = []
        if points and faces:
            for face in faces[start : start + count]:
                if len(face) < 3:
                    continue
                for second, third in zip(face[1:], face[2:], strict=False):
                    triangles.append(Triangle(points[face[0]], points[second], points[third]))
                    indexes.append(len(triangles) - 1)
        groups.append((name, role, indexes))
    return _surface(path.name, str(path), triangles, groups, tuple(item[0] for item in groups))


def _boundary_patches(text: str, path: Path) -> list[tuple[str, str, int, int]]:
    cleaned = _strip_foam(text)
    found: list[tuple[str, str, int, int]] = []
    name = ""
    block: list[str] = []
    depth = 0
    for raw in cleaned.splitlines():
        line = raw.strip()
        if not line or line in {"(", ")"} or line.isdigit():
            continue
        if line.endswith("{") or line == "{":
            depth += 1
            continue
        if line == "}":
            if depth == 1 and name:
                found.append(_boundary_entry(name, block, path))
                name = ""
                block = []
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            name = line
            continue
        if depth >= 1:
            block.append(line)
    if not found:
        raise ImportFailure(
            f"{path / 'constant' / 'polyMesh' / 'boundary'} has no patches.",
            suggestion="Run blockMesh or checkMesh, then import the case again.",
        )
    return found


def _boundary_entry(name: str, block: list[str], path: Path) -> tuple[str, str, int, int]:
    values: dict[str, str] = {}
    for line in block:
        parts = line.replace(";", "").split()
        if len(parts) >= 2:
            values[parts[0]] = parts[1]
    kind = values.get("type", "patch")
    try:
        count = int(values.get("nFaces", "0"))
        start = int(values.get("startFace", "0"))
    except ValueError as exc:
        raise ImportFailure(
            f"Patch {name} in {path.name} has a non-integer nFaces or startFace.",
            suggestion="Rewrite constant/polyMesh/boundary from the mesher that built the case.",
        ) from exc
    return name, guess_role(name, kind), count, start


def _strip_foam(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if "//" in line:
            line = line[: line.index("//")]
        lines.append(line)
    return "\n".join(lines)


def _points(path: Path) -> list[Point]:
    if not path.is_file():
        return []
    points: list[Point] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped.startswith("("):
            continue
        parts = stripped.replace("(", " ").replace(")", " ").split()
        if len(parts) >= 3:
            points.append((float(parts[0]), float(parts[1]), float(parts[2])))
    return points


def _faces(path: Path) -> list[list[int]]:
    if not path.is_file():
        return []
    faces: list[list[int]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if "(" not in stripped:
            continue
        left, _, right = stripped.partition("(")
        if not left.strip().isdigit():
            continue
        indexes = [int(part) for part in right.replace(")", " ").split()]
        faces.append(indexes)
    return faces
