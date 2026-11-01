"""Run-time facts for the GUI: core count, mesh size, memory, progress, force coefficients,
plain-English failure hints and checkMesh bad-cell sets. Qt-free."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

CELLS_PER_RANK = 20_000  # below this, MPI exchange costs more than the extra core gains
GB_PER_MILLION_CELLS = (
    1.0  # steady incompressible RANS rule of thumb; transient/compressible use more
)


def physical_cores() -> int:
    """Logical CPUs / 2. ponytail: assumes 2-way SMT; read lscpu/WMI if that ever misleads."""
    return max(1, (os.cpu_count() or 2) // 2)


def suggest_processes(cells: int, cores: int | None = None) -> int:
    return max(1, min(cores or physical_cores(), cells // CELLS_PER_RANK))


def cell_count(case: Path) -> int:
    """nCells from the polyMesh/owner header note, 0 when there is no mesh yet."""
    owner = case / "constant" / "polyMesh" / "owner"
    if not owner.is_file():
        return 0
    with owner.open(encoding="utf-8", errors="replace") as handle:
        head = handle.read(2000)
    found = re.search(r"nCells:\s*(\d+)", head)
    return int(found.group(1)) if found else 0


def memory_gb(cells: int) -> float:
    return cells / 1e6 * GB_PER_MILLION_CELLS


@dataclass(frozen=True)
class Progress:
    iteration: float
    per_second: float
    eta_seconds: float | None


_TIME = re.compile(r"^Time = ([0-9.eE+-]+)", re.M)
_EXEC = re.compile(r"ExecutionTime = ([0-9.eE+-]+) s")


def progress(log_text: str, end_time: float | None) -> Progress | None:
    """Iterations (or time) per wall-clock second over the last 50 steps, and time to endTime."""
    times = [float(t) for t in _TIME.findall(log_text)]
    clocks = [float(c) for c in _EXEC.findall(log_text)]
    n = min(len(times), len(clocks))
    if n < 2:
        return None
    a = max(0, n - 51)
    dt, dc = times[n - 1] - times[a], clocks[n - 1] - clocks[a]
    rate = dt / dc if dc > 0 else 0.0
    eta = (end_time - times[n - 1]) / rate if end_time and rate > 0 else None
    return Progress(times[n - 1], rate, max(0.0, eta) if eta is not None else None)


def coefficients(case: Path) -> dict[str, list[float]]:
    """Columns of postProcessing/forceCoeffs1/<t>/coefficient*.dat, keyed by header name."""
    files = sorted((case / "postProcessing" / "forceCoeffs1").glob("*/coefficient*.dat"))
    out: dict[str, list[float]] = {}
    names: list[str] = []
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#"):
                parts = line[1:].split()
                if parts and parts[0] == "Time":
                    names = parts
                continue
            values = line.split()
            if names and len(values) == len(names):
                for name, value in zip(names, values, strict=True):
                    out.setdefault(name, []).append(float(value))
    return out


_HINTS = (
    (
        r"cannot find file \S*processor\d+/0/",
        "The parallel run started from time 0, which decomposePar did not write. "
        "Set startFrom latestTime in system/controlDict, or decompose time 0 too.",
    ),
    (
        r"Maximum number of iterations exceeded|bounding \w+, min: -?\d",
        "The solution is diverging. Lower the relaxation factors, use the Robust schemes, "
        "or fix the cells checkMesh flags.",
    ),
    (
        r"Floating point exception|sigFpe",
        "A floating point exception: the solution blew up. Check the mesh quality, "
        "lower the time step or relaxation, and initialise with potentialFoam.",
    ),
    (
        r"Unknown patchField type (\w+)",
        "This OpenFOAM version does not have that boundary condition. "
        "Pick another type or regenerate the case for this version.",
    ),
    (
        r"cannot find file \S*/polyMesh/(points|faces|owner)",
        "There is no mesh. Run blockMesh or snappyHexMesh, or put a mesh in constant/polyMesh.",
    ),
    (
        r"Patch (\w+) not found|Cannot find patchField entry for (\w+)",
        "A field file has no entry for a mesh patch. Send the mesh patch roles to Setup "
        "and write the case again.",
    ),
    (
        r"There are not enough slots available|mpirun.*not found",
        "MPI could not start that many processes. Lower Processes to the physical core count.",
    ),
)


def explain(log_text: str) -> str:
    """Plain-English advice for the first known OpenFOAM failure in the text, else empty."""
    for pattern, hint in _HINTS:
        if re.search(pattern, log_text):
            return hint
    return ""


def bad_cells(case: Path) -> dict[str, list[int]]:
    """checkMesh -writeSets output (constant/polyMesh/sets) as cell ids; face sets map to owners."""
    sets = case / "constant" / "polyMesh" / "sets"
    if not sets.is_dir():
        return {}
    owner: list[int] | None = None
    out: dict[str, list[int]] = {}
    for path in sorted(sets.iterdir()):
        text = path.read_text(encoding="utf-8", errors="replace")
        body = text[text.find("(", text.find("}")) + 1 : text.rfind(")")]
        ids = [int(v) for v in body.split()]
        if "faceSet" in text[:600]:
            if owner is None:
                own = (case / "constant" / "polyMesh" / "owner").read_text(encoding="utf-8")
                owner = [
                    int(v) for v in own[own.find("(", own.find("}")) + 1 : own.rfind(")")].split()
                ]
            ids = sorted({owner[i] for i in ids})
        if ids:
            out[path.name] = ids
    return out
