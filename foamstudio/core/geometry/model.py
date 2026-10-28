"""Imported surfaces and the patch list the case generator consumes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ImportFailure(Exception):
    """A geometry file could not be read. The message names the file and a fix."""

    def __init__(self, message: str, suggestion: str) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"{message}\n\n{suggestion}")


@dataclass(frozen=True)
class Triangle:
    a: tuple[float, float, float]
    b: tuple[float, float, float]
    c: tuple[float, float, float]


@dataclass(frozen=True)
class Patch:
    name: str
    role: str
    triangles: tuple[int, ...]


@dataclass(frozen=True)
class Surface:
    name: str
    source: str
    triangles: tuple[Triangle, ...]
    patches: tuple[Patch, ...]
    zones: tuple[str, ...] = ()

    def patch(self, name: str) -> Patch:
        for item in self.patches:
            if item.name == name:
                return item
        names = ", ".join(item.name for item in self.patches) or "(none)"
        raise ImportFailure(
            f"Patch {name!r} is not on {self.name}.",
            suggestion=f"Choose one of: {names}.",
        )


def guess_role(name: str, boundary_type: str = "") -> str:
    """Map a patch name or OpenFOAM boundary type to a generator role."""
    kind = boundary_type.strip().lower()
    if kind == "symmetryplane":
        return "symmetry"
    if kind in {"empty", "wedge", "symmetry", "cyclic", "wall"}:
        return kind
    lowered = name.lower()
    if "inlet" in lowered or "inflow" in lowered:
        return "inlet"
    if "outlet" in lowered or "outflow" in lowered:
        return "outlet"
    if "sym" in lowered:
        return "symmetry"
    if "empty" in lowered:
        return "empty"
    if "wedge" in lowered:
        return "wedge"
    if kind == "patch":
        return "patch"
    return "wall"


def generator_patches(surface: Surface, selected: str | None = None) -> list[dict[str, str]]:
    """Patch rows for GeneratorSession.set_patches. The picked name is first."""
    rows = [{"name": item.name, "role": item.role} for item in surface.patches]
    if not rows:
        raise ImportFailure(
            f"{surface.name} has no patches.",
            suggestion="Import a file that names its solids, groups, or boundary patches.",
        )
    if selected is None:
        return rows
    if selected not in {row["name"] for row in rows}:
        raise ImportFailure(
            f"Patch {selected!r} is not on {surface.name}.",
            suggestion="Pick a patch that was imported with this geometry.",
        )
    rows.sort(key=lambda row: row["name"] != selected)
    return rows


def import_path(path: Path) -> Surface:
    """Read STL, OBJ, Gmsh, Fluent, STEP, or an OpenFOAM case directory."""
    from foamstudio.core.geometry.io import read_path

    return read_path(path)
