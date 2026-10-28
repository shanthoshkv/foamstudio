"""checkMesh and yPlus log readers. The solvers themselves stay external."""

from __future__ import annotations

import re
from dataclasses import dataclass

_NON_ORTHO = re.compile(r"Mesh non-orthogonality Max:\s*([0-9.eE+-]+)")
_SKEW = re.compile(r"Max skewness = ([0-9.eE+-]+)")
_FAILED = re.compile(r"Failed\s+(\d+)\s+mesh checks")
_YPLUS_AVG = re.compile(
    r"average(?:\s+y\+)?:?\s*([0-9.eE+-]+)",
    re.IGNORECASE,
)
_YPLUS_BARE = re.compile(r"^\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*$")


@dataclass(frozen=True)
class MeshReport:
    ok: bool
    non_ortho: float | None
    skewness: float | None
    failed_checks: int
    summary: str


def parse_check_mesh(text: str) -> MeshReport:
    non_ortho = _last_float(_NON_ORTHO, text)
    skewness = _last_float(_SKEW, text)
    failed = [int(item) for item in _FAILED.findall(text)]
    failed_checks = failed[-1] if failed else 0
    ok = "Mesh OK." in text and failed_checks == 0
    bits = [f"Mesh OK: {ok}"]
    if non_ortho is not None:
        bits.append(f"max non-ortho {non_ortho}")
    if skewness is not None:
        bits.append(f"max skewness {skewness}")
    if failed_checks:
        bits.append(f"failed checks {failed_checks}")
    return MeshReport(ok, non_ortho, skewness, failed_checks, ", ".join(bits))


def _last_float(pattern: re.Pattern[str], text: str) -> float | None:
    found = pattern.findall(text)
    if not found:
        return None
    return float(found[-1])


def gate(
    report: MeshReport,
    *,
    max_non_ortho: float = 70.0,
    max_skewness: float = 4.0,
) -> tuple[bool, str]:
    problems: list[str] = []
    if not report.ok:
        problems.append(report.summary)
    if report.non_ortho is not None and report.non_ortho > max_non_ortho:
        problems.append(f"Max non-orthogonality {report.non_ortho} is above {max_non_ortho}.")
    if report.skewness is not None and report.skewness > max_skewness:
        problems.append(f"Max skewness {report.skewness} is above {max_skewness}.")
    if problems:
        return False, " ".join(problems)
    return True, report.summary


def average_yplus(text: str) -> float | None:
    labelled = _YPLUS_AVG.findall(text)
    if labelled:
        return float(labelled[-1])
    values = [float(match.group(2)) for match in _YPLUS_BARE.finditer(text)]
    if not values:
        return None
    return sum(values) / len(values)
