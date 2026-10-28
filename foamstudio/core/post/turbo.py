"""Turbomachinery numbers from turboForces output.

The case generator writes turboPerf.py. This module reads the same ESI and
Foundation files. It does not write solver dictionaries.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_FLOAT = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class TurboPerformance:
    torque: float
    power: float
    dp0: float | None
    head: float | None
    flow: float | None
    efficiency: float | None
    flavour: str


def _numbers(line: str) -> list[float]:
    return [float(item) for item in _FLOAT.findall(line)]


def last_data_row(text: str) -> list[float] | None:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            numbers = _numbers(stripped)
            if numbers:
                return numbers
    return None


def performance_from_rows(
    *,
    moment: list[float] | None,
    forces: list[float] | None,
    inlet: list[float] | None,
    outlet: list[float] | None,
    flow_row: list[float] | None,
    rho: float,
    omega: float,
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0),
    kinematic_p: bool = True,
) -> TurboPerformance:
    if moment is not None and len(moment) >= 4:
        moment_vector = moment[1:4]
        flavour = "esi"
    elif forces is not None and len(forces) >= 13:
        moment_vector = [forces[7 + index] + forces[10 + index] for index in range(3)]
        flavour = "foundation"
    else:
        raise ValueError(
            "No turboForces moment row was found.\n\n"
            "Run the solver with the turboForces function object, then read "
            "postProcessing/turboForces."
        )
    length = math.sqrt(sum(component * component for component in axis)) or 1.0
    torque = sum(
        component * direction / length
        for component, direction in zip(moment_vector, axis, strict=False)
    )
    power = torque * omega
    dp0 = head = flow = efficiency = None
    if inlet and outlet and len(inlet) >= 5 and len(outlet) >= 5:
        dp0 = _stagnation(outlet, rho, kinematic_p) - _stagnation(inlet, rho, kinematic_p)
        head = dp0 / (rho * 9.80665)
        if flow_row and len(flow_row) >= 2:
            flow = abs(flow_row[1]) / (1.0 if kinematic_p else rho)
            if abs(power) > 0 and flow is not None:
                eta = flow * dp0 / abs(power)
                efficiency = eta if eta <= 1 else 1 / eta
    return TurboPerformance(torque, power, dp0, head, flow, efficiency, flavour)


def _stagnation(row: list[float], rho: float, kinematic_p: bool) -> float:
    pressure = row[1] * (rho if kinematic_p else 1.0)
    speed2 = row[2] ** 2 + row[3] ** 2 + row[4] ** 2
    return pressure + 0.5 * rho * speed2
