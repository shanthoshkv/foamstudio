"""HTML report, GCI, nozzle checks, and validation against reference.json.

PDF is written by the Qt shell with QPdfWriter. This module stays free of Qt.
"""

from __future__ import annotations

import html
import json
import math
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
        f"{problem_block}</body></html>\n"
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
