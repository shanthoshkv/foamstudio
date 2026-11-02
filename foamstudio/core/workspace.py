"""Workspace helpers behind the Tools panel. Qt-free.

Machine/WSL resources and .wslconfig, folder import into a case (whole case or single
0/constant/system folders, geometry, meshes, scripts), script discovery, disk cleanup,
run history, case compare, CSV export, polyMesh/boundary edits, checkMesh table, live
solver monitor, case templates and the update check.
"""

from __future__ import annotations

import csv
import ctypes
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------- resources


def total_memory_gb() -> float:
    if sys.platform == "win32":

        class _Mem(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("load", ctypes.c_ulong),
                ("total", ctypes.c_ulonglong),
                ("avail", ctypes.c_ulonglong),
                ("tpage", ctypes.c_ulonglong),
                ("apage", ctypes.c_ulonglong),
                ("tvirt", ctypes.c_ulonglong),
                ("avirt", ctypes.c_ulonglong),
                ("ext", ctypes.c_ulonglong),
            ]

        mem = _Mem()
        mem.length = ctypes.sizeof(_Mem)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        return float(mem.total) / 2**30
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30


MAX_WSL_FRACTION = 0.75  # leave Windows a quarter: 26 of 32 GB starved it and killed a run


def wslconfig_path() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".wslconfig"


def read_wslconfig(path: Path | None = None) -> dict[str, str]:
    path = path or wslconfig_path()
    values: dict[str, str] = {}
    section = ""
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("["):
                section = line.strip("[]").lower()
            elif "=" in line and section == "wsl2":
                key, value = line.split("=", 1)
                values[key.strip().lower()] = value.strip()
    return values


def write_wslconfig(
    memory_gb: int, processors: int, swap_gb: int, path: Path | None = None
) -> Path:
    """Set memory/processors/swap under [wsl2], keep every other line. Takes effect after
    `wsl --shutdown`."""
    cap = int(total_memory_gb() * MAX_WSL_FRACTION)
    if not 1 <= memory_gb <= cap:
        raise ValueError(f"WSL memory must be 1-{cap} GB (75 % of this machine's RAM).")
    if not 1 <= processors <= (os.cpu_count() or 1):
        raise ValueError(f"Processors must be 1-{os.cpu_count()}.")
    path = path or wslconfig_path()
    wanted = {"memory": f"{memory_gb}GB", "processors": str(processors), "swap": f"{swap_gb}GB"}
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    out: list[str] = []
    section, seen_wsl2 = "", False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if section == "wsl2":
                out.extend(f"{k}={v}" for k, v in wanted.items())
                wanted = {}
            section = stripped.strip("[]").lower()
            seen_wsl2 |= section == "wsl2"
        elif section == "wsl2" and stripped.split("=")[0].strip().lower() in wanted:
            continue
        out.append(line)
    if not seen_wsl2:
        out.append("[wsl2]")
    out.extend(f"{k}={v}" for k, v in wanted.items())
    path.write_text("\n".join(out) + "\n", encoding="ascii")
    return path


def wsl_usage() -> str:
    """`free -h` inside the default distro, or the error text."""
    try:
        done = subprocess.run(
            ["wsl.exe", "--", "free", "-h"], capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"WSL did not answer: {exc}"
    return (done.stdout or done.stderr).strip()


def wsl_shutdown_argv() -> tuple[str, ...]:
    return ("wsl.exe", "--shutdown")


# ---------------------------------------------------------------- import

CASE_PARTS = ("0", "0.orig", "constant", "system")
GEOMETRY = {".stl", ".obj", ".step", ".stp", ".iges", ".igs", ".vtk"}
MESH = {".msh", ".unv", ".cgns", ".ccm"}
SCRIPTS = {".sh", ".py"}


def classify(src: Path) -> str:
    """case | part | geometry | mesh | scripts | files."""
    if src.is_dir() and (src / "system" / "controlDict").is_file():
        return "case"
    if src.is_dir() and src.name in CASE_PARTS:
        return "part"
    if src.is_dir() and any((src / part).is_dir() for part in CASE_PARTS):
        return "part"
    files = [p for p in src.rglob("*") if p.is_file()] if src.is_dir() else [src]
    suffixes = {p.suffix.lower() for p in files}
    if suffixes & MESH:
        return "mesh"
    if suffixes & GEOMETRY:
        return "geometry"
    if suffixes & SCRIPTS or any(p.name.startswith("Allrun") for p in files):
        return "scripts"
    return "files"


def _is_text(path: Path) -> bool:
    try:
        return b"\0" not in path.read_bytes()[:4096]
    except OSError:
        return False


def fix_text(path: Path) -> None:
    """CRLF -> LF for text (bash and OpenFOAM choke on CR); executable bit for scripts."""
    if _is_text(path) and path.suffix.lower() not in {".stl", ".obj", ".msh", ".vtk"}:
        data = path.read_bytes()
        if b"\r\n" in data:
            path.write_bytes(data.replace(b"\r\n", b"\n"))
    if path.name.startswith(("Allrun", "Allclean")) or path.suffix in {".sh", ".py"}:
        path.chmod(path.stat().st_mode | 0o111)


def import_into(src: Path, case: Path) -> tuple[str, list[Path]]:
    """Copy a folder (or file) into a case. A whole case merges at the case root; a 0,
    constant or system folder lands as that folder; a folder holding some of them copies
    each; geometry goes to constant/triSurface, meshes and scripts to the case root."""
    kind = classify(src)
    case.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []

    def put(item: Path, dest: Path) -> None:
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
            copied.extend(p for p in dest.rglob("*") if p.is_file())
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied.append(dest)

    if kind == "case":
        for item in src.iterdir():
            put(item, case / item.name)
    elif kind == "part" and src.name in CASE_PARTS:
        put(src, case / src.name)
    elif kind == "part":
        for item in src.iterdir():
            if item.name in CASE_PARTS or item.is_file():
                put(item, case / item.name)
    elif kind == "geometry":
        items = (
            [p for p in src.rglob("*") if p.suffix.lower() in GEOMETRY] if src.is_dir() else [src]
        )
        for item in items:
            put(item, case / "constant" / "triSurface" / item.name)
    else:
        items = list(src.iterdir()) if src.is_dir() else [src]
        for item in items:
            put(item, case / item.name)
    for path in copied:
        fix_text(path)
    return kind, copied


def wsl_unc(distro: str, linux_path: str) -> Path:
    """\\\\wsl.localhost\\<distro>\\home\\... for a Linux path, writable from Windows."""
    if not linux_path.startswith("/"):
        raise ValueError("A WSL path starts with /, for example /home/me/cases/run1.")
    return Path(rf"\\wsl.localhost\{distro}" + linux_path.replace("/", "\\"))


def list_distros() -> list[str]:
    try:
        done = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    text = done.stdout.decode("utf-16-le", errors="ignore").replace("\0", "")
    return [line.strip() for line in text.splitlines() if line.strip()]


def scripts_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    found = [
        p
        for p in folder.iterdir()
        if p.is_file() and (p.suffix in SCRIPTS or p.name.startswith(("Allrun", "Allclean")))
    ]
    return sorted(found)


def script_command(script: Path) -> str:
    """Command run inside the case directory by the runtime."""
    name = script.name
    if not re.fullmatch(r"[\w.+-]+", name):
        raise ValueError(f"Script name {name!r} has characters the runner will not pass.")
    return f"python3 ./{name}" if script.suffix == ".py" else f"bash ./{name}"


# ---------------------------------------------------------------- disk


def _time_dirs(case: Path) -> list[Path]:
    out = []
    for p in case.iterdir() if case.is_dir() else []:
        try:
            if p.is_dir() and float(p.name) > 0:
                out.append(p)
        except ValueError:
            continue
    return sorted(out, key=lambda p: float(p.name))


def disk_usage(case: Path) -> dict[str, int]:
    def size(p: Path) -> int:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0

    procs = sum(size(p) for p in case.glob("processor*"))
    times = sum(size(p) for p in _time_dirs(case))
    return {
        "total": size(case),
        "processors": procs,
        "time directories": times,
        "postProcessing": size(case / "postProcessing"),
    }


def clean(case: Path, *, processors: bool, keep_latest: bool) -> list[Path]:
    removed: list[Path] = []
    if processors:
        removed += list(case.glob("processor*"))
    if keep_latest:
        removed += _time_dirs(case)[:-1]
    for p in removed:
        shutil.rmtree(p, ignore_errors=True)
    return removed


# ---------------------------------------------------------------- history


def history_path(case: Path) -> Path:
    return case.parent / ".foamstudio" / "history.json"


def record_run(case: Path, name: str, status: str, started: float, ended: float) -> None:
    path = history_path(case)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = load_history(case)
    rows.append(
        {
            "name": name,
            "status": status,
            "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
            "seconds": round(ended - started, 1),
        }
    )
    path.write_text(json.dumps(rows[-200:], indent=1), encoding="utf-8")


def load_history(case: Path) -> list[dict[str, object]]:
    path = history_path(case)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------- compare / export


def compare_cases(left: Path, right: Path) -> str:
    """Unified diff of every text file under 0, constant (not polyMesh) and system."""
    chunks: list[str] = []
    names: set[str] = set()
    for root in (left, right):
        for part in ("0", "constant", "system"):
            for f in (root / part).rglob("*") if (root / part).is_dir() else []:
                rel = f.relative_to(root).as_posix()
                if f.is_file() and "polyMesh" not in rel and _is_text(f):
                    names.add(rel)
    for rel in sorted(names):
        a, b = left / rel, right / rel
        la = a.read_text(encoding="utf-8", errors="replace").splitlines() if a.is_file() else []
        lb = b.read_text(encoding="utf-8", errors="replace").splitlines() if b.is_file() else []
        chunks.extend(difflib.unified_diff(la, lb, f"a/{rel}", f"b/{rel}", lineterm=""))
    return "\n".join(chunks) or "No differences in 0/, constant/ and system/."


def export_csv(columns: dict[str, list[float]], dest: Path) -> Path:
    names = list(columns)
    rows = zip(*(columns[n] for n in names), strict=False)
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(names)
        writer.writerows(rows)
    return dest


def residual_columns(log_text: str) -> dict[str, list[float]]:
    from foamstudio.core.logparse import parse_solver_log

    out: dict[str, list[float]] = {}
    for sample in parse_solver_log(log_text).residuals:
        out.setdefault(f"{sample.field} time", []).append(sample.time)
        out.setdefault(sample.field, []).append(sample.initial)
    return out


# ---------------------------------------------------------------- mesh edits


def boundary_patches(case: Path) -> list[tuple[str, str, int]]:
    """(name, type, nFaces) from constant/polyMesh/boundary."""
    path = case / "constant" / "polyMesh" / "boundary"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    found = re.findall(r"\n\s*(\w+)\s*\{[^}]*?type\s+(\w+);[^}]*?nFaces\s+(\d+);", text)
    return [(n, t, int(f)) for n, t, f in found]


def edit_boundary(case: Path, name: str, *, new_name: str | None, new_type: str | None) -> None:
    """Rename or retype one patch in polyMesh/boundary (the field files must follow)."""
    path = case / "constant" / "polyMesh" / "boundary"
    text = path.read_text(encoding="utf-8")
    block = re.search(rf"(\n\s*){re.escape(name)}(\s*\{{[^}}]*\}})", text)
    if block is None:
        raise ValueError(f"Patch {name!r} is not in {path}.")
    body = block.group(2)
    if new_type:
        if not re.fullmatch(r"\w+", new_type):
            raise ValueError(f"Patch type {new_type!r} is not a word.")
        body = re.sub(r"type\s+\w+;", f"type            {new_type};", body, count=1)
        if new_type != "wall":
            body = re.sub(r"\s*inGroups\s+[^;]*;", "", body)
    label = new_name or name
    if not re.fullmatch(r"\w+", label):
        raise ValueError(f"Patch name {label!r} is not a word.")
    text = text[: block.start()] + block.group(1) + label + body + text[block.end() :]
    path.write_text(text, encoding="utf-8", newline="\n")


_VERTICES = re.compile(r"(\bvertices\s*\()(.*?)(\n\s*\);)", re.S)
_POINT = re.compile(r"\(\s*([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*\)")


def block_vertices(case: Path) -> list[tuple[float, float, float]]:
    """Numeric vertices of system/blockMeshDict (macros/#calc are not supported)."""
    path = case / "system" / "blockMeshDict"
    found = _VERTICES.search(path.read_text(encoding="utf-8")) if path.is_file() else None
    if found is None:
        return []
    return [(float(x), float(y), float(z)) for x, y, z in _POINT.findall(found.group(2))]


def set_block_vertices(case: Path, points: list[tuple[float, float, float]]) -> None:
    """Replace the vertex list; the count must stay the same (blocks index into it)."""
    if len(points) != len(block_vertices(case)):
        raise ValueError("Edit vertices in place: adding or removing them breaks the blocks.")
    path = case / "system" / "blockMeshDict"
    text = path.read_text(encoding="utf-8")
    body = "\n" + "\n".join(f"    ({x!r} {y!r} {z!r})" for x, y, z in points)
    found = _VERTICES.search(text)
    assert found is not None
    text = text[: found.start(2)] + body + text[found.end(2) :]
    path.write_text(text, encoding="utf-8", newline="\n")


@dataclass(frozen=True)
class CheckRow:
    name: str
    value: str
    limit: str
    ok: bool


def check_table(log_text: str) -> list[CheckRow]:
    """checkMesh quality numbers against the usual limits."""
    rows: list[CheckRow] = []

    def num(pattern: str) -> float | None:
        found = re.findall(pattern, log_text)
        return float(found[-1].rstrip(".")) if found else None

    cells = num(r"cells:\s+(\d+)")
    if cells is not None:
        rows.append(CheckRow("cells", f"{int(cells):,}", "", True))
    for name, pattern, limit in (
        ("max non-orthogonality", r"non-orthogonality Max:\s*([\d.eE+-]+)", 70.0),
        ("max skewness", r"Max skewness = ([\d.eE+-]+)", 4.0),
        ("max aspect ratio", r"Max aspect ratio = ([\d.eE+-]+)", 1000.0),
    ):
        value = num(pattern)
        if value is not None:
            rows.append(CheckRow(name, f"{value:.4g}", f"< {limit:g}", value < limit))
    min_vol = num(r"Min volume = ([\d.eE+-]+)")
    if min_vol is not None:
        rows.append(CheckRow("min cell volume", f"{min_vol:.3g}", "> 0", min_vol > 0))
    failed = re.search(r"Failed (\d+) mesh checks", log_text)
    rows.append(CheckRow("checks failed", failed.group(1) if failed else "0", "0", failed is None))
    return rows


# ---------------------------------------------------------------- monitor


def monitor(log_text: str) -> dict[str, float]:
    """Latest Courant number, continuity error and time step from a solver log."""
    out: dict[str, float] = {}
    for key, pattern in (
        ("Courant mean", r"Courant Number mean: ([\d.eE+-]+)"),
        ("Courant max", r"Courant Number mean: [\d.eE+-]+ max: ([\d.eE+-]+)"),
        ("continuity (local)", r"continuity errors : sum local = ([\d.eE+-]+)"),
        ("deltaT", r"^deltaT = ([\d.eE+-]+)"),
    ):
        found = re.findall(pattern, log_text, re.M)
        if found:
            out[key] = float(found[-1])
    return out


# ---------------------------------------------------------------- templates / updates


def templates(repo: Path | None = None) -> dict[str, Path]:
    """Sample case.json files shipped next to the package (source and dev installs)."""
    root = repo or Path(__file__).resolve().parents[2]
    return {f"{p.parent.name}/{p.stem}": p for p in sorted((root / "samples").glob("*/case*.json"))}


RELEASES_FEED = "https://github.com/shanthoshkv/foamstudio/releases.atom"


def check_update(current: str, feed_url: str = RELEASES_FEED) -> str:
    """Fetches the feed only when called (Help > Check for updates)."""
    from urllib.request import urlopen

    from foamstudio.core.update import parse_atom

    with urlopen(feed_url, timeout=15) as response:  # noqa: S310 - fixed https URL
        releases = parse_atom(response.read().decode("utf-8"))
    if not releases:
        return f"No releases published yet. You have {current}."
    latest = releases[0]
    if latest.version.lstrip("v") == current:
        return f"FoamStudio {current} is the latest version."
    return f"FoamStudio {latest.version} is available: {latest.url}"
