"""Unit-aware number entry: "10 km/h", "2.5 mm", "1 atm", "20 C" -> SI floats."""

from __future__ import annotations

import re

# unit -> (dimension, factor to SI, offset). Temperature is affine: K = v * factor + offset.
_UNITS: dict[str, tuple[str, float, float]] = {
    **{
        u: ("length", f, 0)
        for u, f in {
            "m": 1,
            "cm": 1e-2,
            "mm": 1e-3,
            "um": 1e-6,
            "km": 1e3,
            "in": 0.0254,
            "ft": 0.3048,
            "c": 1.0,
        }.items()
    },
    **{
        u: ("velocity", f, 0)
        for u, f in {
            "m/s": 1,
            "km/h": 1 / 3.6,
            "kph": 1 / 3.6,
            "mph": 0.44704,
            "kn": 0.514444,
            "kt": 0.514444,
            "ft/s": 0.3048,
        }.items()
    },
    **{u: ("time", f, 0) for u, f in {"s": 1, "ms": 1e-3, "min": 60, "h": 3600}.items()},
    **{
        u: ("pressure", f, 0)
        for u, f in {
            "pa": 1,
            "kpa": 1e3,
            "mpa": 1e6,
            "bar": 1e5,
            "atm": 101325,
            "psi": 6894.757,
        }.items()
    },
    **{u: ("angle", f, 0) for u, f in {"deg": 1, "°": 1, "rad": 57.29577951308232}.items()},
    "k": ("temperature", 1, 0),
    "degc": ("temperature", 1, 273.15),
    "degf": ("temperature", 5 / 9, 255.3722222222222),
}
_NUMBER = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*?)\s*$")


def parse_quantity(text: str, dimension: str) -> float:
    """Number in SI for `dimension`; a bare number is taken as already SI (degrees for angle)."""
    match = _NUMBER.match(text)
    if match is None:
        raise ValueError(f"{text!r} is not a number")
    value, unit = float(match.group(1)), match.group(2).lower().replace(" ", "")
    if not unit:
        return value
    if dimension == "temperature" and unit in ("c", "°c"):
        unit = "degc"
    unit = {"°f": "degf", "f": "degf"}.get(unit, unit) if dimension == "temperature" else unit
    if dimension == "length" and unit == "c":
        raise ValueError("chord lengths need a chord size; give metres")
    known = _UNITS.get(unit)
    if known is None or known[0] != dimension:
        options = sorted(u for u, (d, _f, _o) in _UNITS.items() if d == dimension and u != "c")
        raise ValueError(f"Unknown {dimension} unit {unit!r}. Use one of: {', '.join(options)}")
    return value * known[1] + known[2]


if __name__ == "__main__":
    assert parse_quantity("36 km/h", "velocity") == 10
    assert parse_quantity("2.5 mm", "length") == 0.0025
    assert abs(parse_quantity("20 C", "temperature") - 293.15) < 1e-9
    assert parse_quantity("1 atm", "pressure") == 101325
    assert parse_quantity("1.5", "length") == 1.5
    print("units ok")
