"""NACA 0012 C-mesh (6 hex blocks) for blockMesh.

    python nacamesh.py OUT_blockMeshDict [first_cell]

Chord 1, leading edge at the origin, far field radius 50 c centred on the trailing edge,
wake to x = 51. First cell height defaults to 4e-6 c (y+ ~ 1 at Re 6e6). Closed trailing
edge (-0.1036 coefficient). Patches: airfoil (wall), inlet (C arc and far-field lines),
outlet (wake exit), frontAndBack (empty, z = 0 and 1 so Aref = 1).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

R = 50.0  # far field radius
XS = 0.3  # chordwise block split
N_FRONT, N_AFT, N_NORMAL, N_WAKE = 70, 100, 150, 110


def thickness(x: float) -> float:
    return 0.6 * (
        0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4
    )


def normal_grading(first: float, n: int, length: float) -> float:
    """Total expansion ratio (last/first) of n geometric cells over length with this first cell."""
    lo, hi = 1.000001, 2.0
    for _ in range(200):
        r = (lo + hi) / 2
        if length * (r - 1) / (r**n - 1) > first:
            lo = r
        else:
            hi = r
    return r ** (n - 1)


def spline(a: int, b: int, x0: float, x1: float, sign: float, n: int = 40) -> str:
    """Interior airfoil points between x0 and x1 with cosine clustering at both ends."""
    pts = []
    for i in range(1, n):
        t = i / n
        x = x0 + (x1 - x0) * 0.5 * (1 - math.cos(math.pi * t))
        y = sign * thickness(x)
        pts.append(f"({x!r} {y!r} {{z}})")
    body = " ".join(pts)
    return body


def main() -> None:
    out = Path(sys.argv[1])
    first = float(sys.argv[2]) if len(sys.argv) > 2 else 4e-6
    g_normal = normal_grading(first, N_NORMAL, R)
    ys = thickness(XS)
    arc_y = math.sqrt(R**2 - (XS - 1) ** 2)
    base = [
        (0.0, 0.0),  # 0 leading edge
        (XS, ys),  # 1 upper split
        (1.0, 0.0),  # 2 trailing edge
        (XS, -ys),  # 3 lower split
        (1 - R, 0.0),  # 4 far field front
        (XS, arc_y),  # 5 far field above split
        (1.0, R),  # 6 far field above TE
        (XS, -arc_y),  # 7 far field below split
        (1.0, -R),  # 8 far field below TE
        (1 + R, 0.0),  # 9 wake end
        (1 + R, R),  # 10
        (1 + R, -R),  # 11
    ]
    verts = [(x, y, 0.0) for x, y in base] + [(x, y, 1.0) for x, y in base]
    o = len(base)

    def hexa(v: tuple[int, int, int, int], cells: tuple[int, int], grading: tuple[str, str]) -> str:
        a, b, c, d = v
        return (
            f"    hex ({a} {b} {c} {d} {a + o} {b + o} {c + o} {d + o}) "
            f"({cells[0]} {cells[1]} 1) simpleGrading ({grading[0]} {grading[1]} 1)"
        )

    gn = f"{g_normal!r}"
    # Wake blocks: wall spacing at the trailing edge, relaxed to 1e-3 at the outflow, so far-wake
    # cells are not 4e-6 thick (aspect ratio ~6e5 stalls the pressure solver).
    gfar = f"{normal_grading(1e-3, N_NORMAL, R)!r}"

    def hexa_edges(v: tuple[int, int, int, int], cells: tuple[int, int], grading: str) -> str:
        a, b, c, d = v
        return (
            f"    hex ({a} {b} {c} {d} {a + o} {b + o} {c + o} {d + o}) "
            f"({cells[0]} {cells[1]} 1) edgeGrading ({grading} 1 1 1 1)"
        )

    g_le = "8"  # front blocks: cells grow away from the leading edge
    g_te = "0.2"  # aft blocks: cells shrink toward the trailing edge
    g_wake = "200"
    blocks = [
        hexa((0, 1, 5, 4), (N_FRONT, N_NORMAL), (g_le, gn)),
        hexa((1, 2, 6, 5), (N_AFT, N_NORMAL), (g_te, gn)),
        hexa_edges(
            (2, 9, 10, 6),
            (N_WAKE, N_NORMAL),
            f"{g_wake} {g_wake} {g_wake} {g_wake} {gn} {gfar} {gfar} {gn}",
        ),
        hexa((0, 4, 7, 3), (N_NORMAL, N_FRONT), (gn, g_le)),
        hexa((3, 7, 8, 2), (N_NORMAL, N_AFT), (gn, g_te)),
        hexa_edges(
            (2, 8, 11, 9),
            (N_NORMAL, N_WAKE),
            f"{gn} {gfar} {gfar} {gn} {g_wake} {g_wake} {g_wake} {g_wake}",
        ),
    ]

    def arc_point(angle_deg: float, z: float) -> str:
        a = math.radians(angle_deg)
        return f"({1 + R * math.cos(a)!r} {R * math.sin(a)!r} {z})"

    ang_split = math.degrees(math.atan2(arc_y, XS - 1))
    edges = []
    for z, off in ((0.0, 0), (1.0, o)):
        edges.append(f"    spline {0 + off} {1 + off} ({spline(0, 1, 0.0, XS, 1).format(z=z)})")
        edges.append(f"    spline {1 + off} {2 + off} ({spline(1, 2, XS, 1.0, 1).format(z=z)})")
        edges.append(f"    spline {0 + off} {3 + off} ({spline(0, 3, 0.0, XS, -1).format(z=z)})")
        edges.append(f"    spline {3 + off} {2 + off} ({spline(3, 2, XS, 1.0, -1).format(z=z)})")
        edges.append(f"    arc {4 + off} {5 + off} {arc_point((180 + ang_split) / 2, z)}")
        edges.append(f"    arc {5 + off} {6 + off} {arc_point((ang_split + 90) / 2, z)}")
        edges.append(f"    arc {4 + off} {7 + off} {arc_point(-(180 + ang_split) / 2, z)}")
        edges.append(f"    arc {7 + off} {8 + off} {arc_point(-(ang_split + 90) / 2, z)}")

    def face(a: int, b: int) -> str:
        return f"            ({a} {b} {b + o} {a + o})"

    airfoil = [face(0, 1), face(1, 2), face(0, 3), face(3, 2)]
    inlet = [face(4, 5), face(5, 6), face(6, 10), face(4, 7), face(7, 8), face(8, 11)]
    outlet = [face(10, 9), face(9, 11)]

    def patch(name: str, kind: str, faces: list[str]) -> str:
        joined = "\n".join(faces)
        return f"    {name}\n    {{\n        type {kind};\n        faces\n        (\n{joined}\n        );\n    }}"

    text = "\n".join(
        [
            "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n"
            "    object blockMeshDict;\n}\n",
            "scale 1;\n",
            "vertices\n(\n" + "\n".join(f"    ({x!r} {y!r} {z!r})" for x, y, z in verts) + "\n);\n",
            "blocks\n(\n" + "\n".join(blocks) + "\n);\n",
            "edges\n(\n" + "\n".join(edges) + "\n);\n",
            "defaultPatch\n{\n    name frontAndBack;\n    type empty;\n}\n",
            "boundary\n(\n"
            + "\n".join(
                [patch("airfoil", "wall", airfoil), patch("inlet", "patch", inlet),
                 patch("outlet", "patch", outlet)]
            )
            + "\n);\n",
        ]
    )
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"normal grading {g_normal:.4g} for first cell {first:g}")


if __name__ == "__main__":
    main()
