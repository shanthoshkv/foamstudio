"""Residuals, Courant number, and force monitors. ESI and Foundation share these lines."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TIME = re.compile(r"^Time\s*=\s*([+-]?[0-9.eE+-]+)\s*$")
_RESIDUAL = re.compile(
    r"Solving for (\w+), Initial residual = ([+-]?[0-9.eE+-]+), "
    r"Final residual = ([+-]?[0-9.eE+-]+)"
)
_COURANT = re.compile(r"Courant Number mean:\s*([+-]?[0-9.eE+-]+)\s+max:\s*([+-]?[0-9.eE+-]+)")
_FLOAT = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class ResidualSample:
    time: float
    field: str
    initial: float
    final: float


@dataclass(frozen=True)
class CourantSample:
    time: float
    mean: float
    maximum: float


@dataclass(frozen=True)
class MonitorSample:
    time: float
    name: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class LogSnapshot:
    residuals: tuple[ResidualSample, ...]
    courant: tuple[CourantSample, ...]
    monitors: tuple[MonitorSample, ...]


def parse_solver_log(text: str) -> LogSnapshot:
    residuals: list[ResidualSample] = []
    courant: list[CourantSample] = []
    time = 0.0
    seen_time = False
    for line in text.splitlines():
        time_match = _TIME.match(line.strip())
        if time_match is not None:
            time = float(time_match.group(1))
            seen_time = True
            continue
        residual = _RESIDUAL.search(line)
        if residual is not None and seen_time:
            residuals.append(
                ResidualSample(
                    time,
                    residual.group(1),
                    float(residual.group(2)),
                    float(residual.group(3)),
                )
            )
            continue
        courant_match = _COURANT.search(line)
        if courant_match is not None and seen_time:
            courant.append(
                CourantSample(
                    time,
                    float(courant_match.group(1)),
                    float(courant_match.group(2)),
                )
            )
    return LogSnapshot(tuple(residuals), tuple(courant), ())


def parse_monitor_table(text: str, *, name: str) -> tuple[MonitorSample, ...]:
    """Numeric rows from postProcessing dat files. Comment lines are skipped."""
    samples: list[MonitorSample] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("("):
            continue
        numbers = [float(item) for item in _FLOAT.findall(stripped)]
        if len(numbers) < 2:
            continue
        samples.append(MonitorSample(numbers[0], name, tuple(numbers[1:])))
    return tuple(samples)
