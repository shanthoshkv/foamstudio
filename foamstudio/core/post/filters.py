"""Slice, clip, iso-lines, and a cartesian streamline. No VTK import."""

from __future__ import annotations

from collections.abc import Callable

Vec = tuple[float, float, float]
Tri = tuple[Vec, Vec, Vec]


def _dot(left: Vec, right: Vec) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _sub(left: Vec, right: Vec) -> Vec:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _add(left: Vec, right: Vec) -> Vec:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def _scale(vector: Vec, factor: float) -> Vec:
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _side(point: Vec, origin: Vec, normal: Vec) -> float:
    return _dot(_sub(point, origin), normal)


def _centroid(triangle: Tri) -> Vec:
    return (
        (triangle[0][0] + triangle[1][0] + triangle[2][0]) / 3.0,
        (triangle[0][1] + triangle[1][1] + triangle[2][1]) / 3.0,
        (triangle[0][2] + triangle[1][2] + triangle[2][2]) / 3.0,
    )


def clip_triangles(
    triangles: tuple[Tri, ...] | list[Tri],
    origin: Vec,
    normal: Vec,
) -> list[Tri]:
    """Keep triangles whose centroid is on the positive side of the plane."""
    return [triangle for triangle in triangles if _side(_centroid(triangle), origin, normal) >= 0.0]


def slice_segments(
    triangles: tuple[Tri, ...] | list[Tri],
    origin: Vec,
    normal: Vec,
) -> list[tuple[Vec, Vec]]:
    """Line segments where each triangle crosses the plane."""
    segments: list[tuple[Vec, Vec]] = []
    for triangle in triangles:
        hits = _plane_hits(triangle, origin, normal)
        if len(hits) >= 2:
            segments.append((hits[0], hits[1]))
    return segments


def _plane_hits(triangle: Tri, origin: Vec, normal: Vec) -> list[Vec]:
    hits: list[Vec] = []
    edges = (
        (triangle[0], triangle[1]),
        (triangle[1], triangle[2]),
        (triangle[2], triangle[0]),
    )
    for start, end in edges:
        start_side = _side(start, origin, normal)
        end_side = _side(end, origin, normal)
        if start_side == 0.0 and end_side == 0.0:
            continue
        if start_side * end_side > 0.0:
            continue
        span = start_side - end_side
        if span == 0.0:
            continue
        blend = start_side / span
        if 0.0 <= blend <= 1.0:
            hits.append(_add(start, _scale(_sub(end, start), blend)))
    return hits


def iso_segments(
    triangles: tuple[tuple[Tri, tuple[float, float, float]], ...]
    | list[tuple[Tri, tuple[float, float, float]]],
    value: float,
) -> list[tuple[Vec, Vec]]:
    """Segments where a per-vertex scalar crosses `value`."""
    segments: list[tuple[Vec, Vec]] = []
    for triangle, scalars in triangles:
        hits = _iso_hits(triangle, scalars, value)
        if len(hits) >= 2:
            segments.append((hits[0], hits[1]))
    return segments


def _iso_hits(triangle: Tri, scalars: tuple[float, float, float], value: float) -> list[Vec]:
    hits: list[Vec] = []
    edges = ((0, 1), (1, 2), (2, 0))
    for left, right in edges:
        low = scalars[left] - value
        high = scalars[right] - value
        if low == 0.0 and high == 0.0:
            continue
        if low * high > 0.0:
            continue
        span = low - high
        if span == 0.0:
            continue
        blend = low / span
        if 0.0 <= blend <= 1.0:
            hits.append(_add(triangle[left], _scale(_sub(triangle[right], triangle[left]), blend)))
    return hits


def streamline(
    start: Vec,
    velocity: Callable[[Vec], Vec | None],
    *,
    steps: int,
    dt: float,
) -> list[Vec]:
    """RK2 on a cartesian field. `velocity` returns None at the edge of the field."""
    if steps < 1 or dt <= 0:
        raise ValueError("Streamline steps must be at least 1 and dt must be positive.")
    points = [start]
    current = start
    for _ in range(steps):
        first = velocity(current)
        if first is None:
            break
        mid = _add(current, _scale(first, 0.5 * dt))
        second = velocity(mid)
        if second is None:
            break
        current = _add(current, _scale(second, dt))
        points.append(current)
    return points
