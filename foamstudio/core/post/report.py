"""HTML report, GCI, nozzle checks, and validation against reference.json.

PDF is written by the Qt shell with QPdfWriter. This module stays free of Qt.
"""

from __future__ import annotations

import contextlib
import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path


class ReportFailure(Exception):
    def __init__(self, message: str, suggestion: str) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"{message}\n\n{suggestion}")


def gci_fine(
    fine: float,
    medium: float,
    coarse: float,
    ratio: float,
    *,
    factor: float = 1.25,
) -> float:
    """Roache GCI on the fine mesh. `ratio` is the refinement ratio h_coarse/h_fine (> 1)."""
    if ratio <= 1:
        raise ReportFailure(
            f"Refinement ratio {ratio} is not greater than 1.",
            suggestion="Order the three meshes fine, medium, coarse with a constant ratio above 1.",
        )
    eps21 = medium - fine
    eps32 = coarse - medium
    if eps21 == 0 or eps32 == 0:
        raise ReportFailure(
            "Two mesh levels produced the same value, so the observed order is undefined.",
            suggestion="Use three meshes whose integral values actually change.",
        )
    order = math.log(abs(eps32 / eps21)) / math.log(ratio)
    denominator = ratio**order - 1
    if denominator == 0:
        raise ReportFailure(
            "The GCI denominator is zero.",
            suggestion="Check the refinement ratio and the three mesh values.",
        )
    return float(factor * abs(eps21) / denominator)


def area_ratio(mach: float, gamma: float = 1.4) -> float:
    if mach <= 0:
        raise ReportFailure(
            "Mach must be positive.",
            suggestion="Use the subsonic branch below 1 or the supersonic branch above 1.",
        )
    term = (2 / (gamma + 1)) * (1 + 0.5 * (gamma - 1) * mach * mach)
    exponent = (gamma + 1) / (2 * (gamma - 1))
    return float((1 / mach) * term**exponent)


def mach_from_area(area: float, *, supersonic: bool, gamma: float = 1.4) -> float:
    if area < 1:
        raise ReportFailure(
            f"A/A* = {area} is below 1, which is not a physical isentropic area.",
            suggestion=(
                "Throat area ratio is 1. Values above 1 have a subsonic and a supersonic Mach."
            ),
        )
    if abs(area - 1.0) < 1e-9:
        return 1.0
    if supersonic:
        low, high = 1.0000001, 20.0
    else:
        low, high = 1e-6, 0.999999
    for _ in range(80):
        mid = 0.5 * (low + high)
        if area_ratio(mid, gamma) > area:
            if supersonic:
                high = mid
            else:
                low = mid
        else:
            if supersonic:
                low = mid
            else:
                high = mid
    return 0.5 * (low + high)


def pressure_ratio(mach: float, gamma: float = 1.4) -> float:
    ratio = (1 + 0.5 * (gamma - 1) * mach * mach) ** (-gamma / (gamma - 1))
    return float(ratio)


@dataclass(frozen=True)
class ReportInputs:
    title: str
    solver: str
    mesh_summary: str
    residual_final: float | None
    integrals: tuple[tuple[str, float], ...]
    yplus: float | None
    gci: float | None
    validation: tuple[str, ...]
    problems: tuple[str, ...] = ()
    provenance: tuple[tuple[str, str], ...] = ()


def render_html(report: ReportInputs) -> str:
    def row(label: str, value: str) -> str:
        return f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"

    integral_rows = "".join(row(name, f"{value:.6g}") for name, value in report.integrals)
    checks = (
        "".join(f"<li>{html.escape(item)}</li>" for item in report.validation) or "<li>None.</li>"
    )
    problems = "".join(f"<li>{html.escape(item)}</li>" for item in report.problems)
    problem_block = f"<h2>Problems</h2><ul>{problems}</ul>" if problems else ""
    residual = "not recorded" if report.residual_final is None else f"{report.residual_final:.6g}"
    yplus = "not recorded" if report.yplus is None else f"{report.yplus:.6g}"
    gci = "not recorded" if report.gci is None else f"{report.gci:.6g}"
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(report.title)}</title></head><body>"
        f"<h1>{html.escape(report.title)}</h1>"
        "<h2>Setup</h2><table>"
        f"{row('Solver', report.solver)}</table>"
        "<h2>Mesh</h2>"
        f"<p>{html.escape(report.mesh_summary)}</p>"
        "<h2>Convergence</h2><table>"
        f"{row('Final residual', residual)}</table>"
        f"<h2>Integrals</h2><table>{integral_rows}</table>"
        "<h2>y+</h2><table>"
        f"{row('y+', yplus)}</table>"
        "<h2>GCI</h2><table>"
        f"{row('GCI fine', gci)}</table>"
        f"<h2>Validation</h2><ul>{checks}</ul>"
        f"{problem_block}"
        + (
            "<h2>Provenance</h2><table>"
            + "".join(row(k, v) for k, v in report.provenance)
            + "</table>"
            if report.provenance
            else ""
        )
        + "</body></html>\n"
    )


def write_html(report: ReportInputs, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_html(report), encoding="utf-8", newline="\n")
    return destination


@dataclass(frozen=True)
class SeriesPoint:
    x: float
    y: float


def compare_series(
    reference: tuple[SeriesPoint, ...],
    actual: tuple[SeriesPoint, ...],
    tolerance: float,
) -> list[str]:
    problems: list[str] = []
    for point in reference:
        nearest = min(actual, key=lambda item: abs(item.x - point.x), default=None)
        if nearest is None or abs(nearest.x - point.x) > 1e-6:
            problems.append(f"No sample at x={point.x}.")
            continue
        if abs(nearest.y - point.y) > tolerance:
            problems.append(
                f"At x={point.x}, value {nearest.y} differs from {point.y} "
                f"by more than {tolerance}."
            )
    return problems


def compare_scalar(name: str, actual: float, expected: float, tolerance: float) -> list[str]:
    if abs(actual - expected) > tolerance:
        return [f"{name} {actual} differs from {expected} by more than {tolerance}."]
    return []


_APPLICATION = re.compile(r"(?m)^\s*application\s+([A-Za-z_][A-Za-z0-9_]*)\s*;")


def inputs_for_case(title: str, case_dir: Path) -> ReportInputs:
    """Report fields from files a run already wrote. This does not write dictionaries."""
    from foamstudio.core.logparse import parse_solver_log
    from foamstudio.core.mesh.check import parse_check_mesh

    solver = "recorded in system/controlDict"
    control = case_dir / "system" / "controlDict"
    if control.is_file():
        match = _APPLICATION.search(control.read_text(encoding="utf-8", errors="replace"))
        if match is not None:
            solver = match.group(1)

    mesh_summary = "See case/log.checkMesh when checkMesh has been run."
    check_log = case_dir / "log.checkMesh"
    if check_log.is_file():
        mesh_summary = parse_check_mesh(
            check_log.read_text(encoding="utf-8", errors="replace")
        ).summary

    # Allrun's runApplication writes log.<application>; log.solver is FoamStudio's own name.
    log_path = case_dir / "log.solver"
    if not log_path.is_file() and (case_dir / f"log.{solver}").is_file():
        log_path = case_dir / f"log.{solver}"
    residual = None
    problems: tuple[str, ...] = ()
    if log_path.is_file():
        snapshot = parse_solver_log(log_path.read_text(encoding="utf-8", errors="replace"))
        if snapshot.residuals:
            residual = snapshot.residuals[-1].initial
    else:
        problems = (
            f"No solver log was found at {log_path}.",
            "Run the case, then write the report again.",
        )
    return ReportInputs(
        title=title,
        solver=solver,
        mesh_summary=mesh_summary,
        residual_final=residual,
        integrals=_force_integrals(case_dir),
        yplus=_case_yplus(case_dir),
        gci=None,
        validation=(),
        problems=problems,
        provenance=_provenance(case_dir, log_path),
    )


_BUILD = re.compile(r"(?m)^Build\s*:\s*(.+)$")
_VERSION = re.compile(r"(?m)^\|\s+\\\\\s+/\s+O peration\s+\|\s+Version:\s+(\S+)")


def _provenance(case_dir: Path, log_path: Path) -> tuple[tuple[str, str], ...]:
    """What produced these numbers: spec hash, generator, OpenFOAM build, FoamStudio."""
    import hashlib

    from foamstudio import __version__

    rows: list[tuple[str, str]] = [("FoamStudio", __version__)]
    spec = case_dir / "case.json"
    if spec.is_file():
        data = spec.read_bytes()
        rows.append(("case.json sha256", hashlib.sha256(data).hexdigest()))
        with contextlib.suppress(ValueError, AttributeError):
            rows.append(("Generator", str(json.loads(data).get("generator", "unknown"))))
    if log_path.is_file():
        head = log_path.read_text(encoding="utf-8", errors="replace")[:4000]
        for label, pattern in (("OpenFOAM version", _VERSION), ("OpenFOAM build", _BUILD)):
            match = pattern.search(head)
            if match is not None:
                rows.append((label, match.group(1).strip()))
    return tuple(rows)


def _case_yplus(case_dir: Path) -> float | None:
    from foamstudio.core.mesh.check import average_yplus

    candidates = [case_dir / "log.yPlus", case_dir / "log.yPlusCheck"]
    post = case_dir / "postProcessing"
    if post.is_dir():
        candidates.extend(
            path
            for path in sorted(post.rglob("*"))
            if path.is_file() and "yplus" in path.name.lower()
        )
    for path in candidates:
        if not path.is_file():
            continue
        value = average_yplus(path.read_text(encoding="utf-8", errors="replace"))
        if value is not None:
            return float(value)
    return None


def _force_integrals(case_dir: Path) -> tuple[tuple[str, float], ...]:
    from foamstudio.core.logparse import parse_monitor_table

    post = case_dir / "postProcessing"
    if not post.is_dir():
        return ()
    files = [
        path
        for path in sorted(post.rglob("*"))
        if path.is_file() and path.stem.lower().startswith("forces")
    ]
    best_time: float | None = None
    best: tuple[float, ...] | None = None
    for path in files:
        samples = parse_monitor_table(
            path.read_text(encoding="utf-8", errors="replace"), name=path.stem
        )
        if not samples:
            continue
        sample = samples[-1]
        if len(sample.values) < 3:
            continue
        if best_time is None or sample.time >= best_time:
            best_time = sample.time
            best = sample.values[:3]
    if best is None:
        return ()
    return tuple(
        (label, float(value))
        for label, value in zip(("force x", "force y", "force z"), best, strict=True)
    )


def load_reference(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportFailure(
            f"Could not read {path}: {exc}",
            suggestion="Restore samples/<name>/reference.json from the repository.",
        ) from exc
    if not isinstance(raw, dict):
        raise ReportFailure(
            f"{path} is not a JSON object.",
            suggestion="Keep citation, tolerance, and the reference values in one object.",
        )
    return raw
