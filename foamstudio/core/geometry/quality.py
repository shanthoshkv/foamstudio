"""Colour-blind-safe mesh colours. Viridis stops, no plotting library."""

from __future__ import annotations

from collections.abc import Sequence

_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.0, (68, 1, 84)),
    (0.25, (59, 82, 139)),
    (0.5, (33, 145, 140)),
    (0.75, (94, 201, 98)),
    (1.0, (253, 231, 37)),
)


def _mix(
    left: tuple[int, int, int], right: tuple[int, int, int], blend: float
) -> tuple[int, int, int]:
    return (
        int(round(left[0] + (right[0] - left[0]) * blend)),
        int(round(left[1] + (right[1] - left[1]) * blend)),
        int(round(left[2] + (right[2] - left[2]) * blend)),
    )


def colour_ramp(value: float, low: float, high: float) -> tuple[int, int, int]:
    """Map `value` into the viridis stops. `low` is purple and `high` is yellow."""
    fraction = 0.0 if high <= low else min(1.0, max(0.0, (value - low) / (high - low)))
    for index, (right_t, right) in enumerate(_STOPS[1:], start=1):
        left_t, left = _STOPS[index - 1]
        if fraction <= right_t:
            span = right_t - left_t
            blend = 0.0 if span == 0 else (fraction - left_t) / span
            return _mix(left, right, blend)
    return _STOPS[-1][1]


def colour_values(values: Sequence[float]) -> list[tuple[int, int, int]]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    return [colour_ramp(item, low, high) for item in values]
