"""NACA 0012 C-mesh (12 hex blocks) for blockMesh.

    python nacamesh.py OUT_blockMeshDict [first_cell] [scale]

Chord 1, leading edge at the origin, far field radius 50 c centred on the trailing edge,
wake to x = 51. First cell height defaults to 4e-6 c (y+ ~ 1 at Re 6e6). Closed trailing
edge (-0.1036 coefficient). Patches: airfoil (wall), inlet (C arc and far-field lines),
outlet (wake exit), frontAndBack (empty, z = 0 and 1 so Aref = 1).

A wall layer 0.02 c thick is built from the surface normal offset, so grid lines leave the
wall at right angles. The earlier single-layer C-mesh joined the wall straight to the far
field: wall cells were ~30 deg non-orthogonal on average and drag came out ~70 % high.
`scale` multiplies every cell count (2 = twice as fine in each direction) for GCI studies.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

R = 50.0  # far field radius
XS = 0.3  # chordwise block split
SPLIT_DEG = 120.0  # far-field point that pairs with the chordwise split
D0, D1 = 0.004, 0.02  # wall layer thickness at the LE and TE (tracks boundary-layer growth)
DW = 0.5  # wall layer half-thickness at the wake exit
N_FRONT, N_AFT, N_IN, N_OUT, N_WAKE = 70, 100, 70, 90, 110


def thickness(x: float) -> float:
    return 0.6 * (
        0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4
    )


def normal(x: float, sign: float) -> tuple[float, float]:
    """Outward unit normal of the upper (sign 1) or lower (sign -1) surface at x."""
    h = 1e-7
    a, b = max(x - h, 0.0), min(x + h, 1.0)
    dt = (thickness(b) - thickness(a)) / (b - a)
    s = math.hypot(dt, 1.0)
    return -dt / s, sign / s


def layer(x: float) -> float:
    """Wall layer thickness. Thin at the LE so the offset curve's arc length tracks the surface."""
    return D0 + (D1 - D0) * x


def surface(x: float, sign: float, off: bool = False) -> tuple[float, float]:
    nx, ny = normal(x, sign) if off else (0.0, 0.0)
    d = layer(x) if off else 0.0
    return x + d * nx, sign * thickness(x) + d * ny


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


def curve(x0: float, x1: float, sign: float, off: bool, z: float, n: int = 40) -> str:
    """Interior points of the surface (or its normal offset) with cosine clustering."""
    pts = []
    for i in range(1, n):
        x = x0 + (x1 - x0) * 0.5 * (1 - math.cos(math.pi * i / n))
        px, py = surface(x, sign, off)
        pts.append(f"({px!r} {py!r} {z})")
    return " ".join(pts)


def arclength(x0: float, x1: float, sign: float, off: bool, m: int = 4000) -> tuple[list[float], list[float]]:
    xs = [x0 + (x1 - x0) * 0.5 * (1 - math.cos(math.pi * i / m)) for i in range(m + 1)]
    pts = [surface(x, sign, off) for x in xs]
    ss = [0.0]
    for (ax, ay), (bx, by) in zip(pts, pts[1:], strict=False):
        ss.append(ss[-1] + math.hypot(bx - ax, by - ay))
    return xs, ss


def interp(v: float, xs: list[float], ys: list[float]) -> float:
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if xs[mid] <= v else (lo, mid)
    t = (v - xs[lo]) / (xs[hi] - xs[lo])
    return ys[lo] + t * (ys[hi] - ys[lo])


def matched(x0: float, x1: float, ratio: float, n: int) -> tuple[str, str]:
    """Multi-gradings for the surface edge and its offset with nodes at the same chord x.

    blockMesh spaces nodes by arc length. The offset curve is relatively longer round the LE,
    so plain gradings shift its nodes downstream and tilt the wall cells ~45 deg.
    """
    r = ratio ** (1 / (n - 1)) if n > 1 else 1.0
    w = [r**i for i in range(n)]
    xs, ss = arclength(x0, x1, 1, False)
    s_nodes = [ss[-1] * sum(w[:i]) / sum(w) for i in range(n + 1)]
    x_nodes = [interp(s, ss, xs) for s in s_nodes]
    xo, so = arclength(x0, x1, 1, True)
    o_nodes = [interp(x, xo, so) for x in x_nodes]

    def sections(nodes: list[float]) -> str:
        total = nodes[-1] - nodes[0]
        return "(" + " ".join(f"({(b - a) / total!r} 1 1)" for a, b in zip(nodes, nodes[1:], strict=False)) + ")"

    return sections(s_nodes), sections(o_nodes)


def main() -> None:
    out = Path(sys.argv[1])
    first = float(sys.argv[2]) if len(sys.argv) > 2 else 4e-6
    k = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    nf, na, ni, no, nw = (max(1, round(n * k)) for n in (N_FRONT, N_AFT, N_IN, N_OUT, N_WAKE))
    first /= k

    split = math.radians(SPLIT_DEG)
    arc_x, arc_y = 1 + R * math.cos(split), R * math.sin(split)
    nu_te, nl_te = normal(1.0, 1), normal(1.0, -1)
    base = [
        (0.0, 0.0),  # 0 leading edge
        surface(XS, 1),  # 1 upper split
        (1.0, 0.0),  # 2 trailing edge
        surface(XS, -1),  # 3 lower split
        (1 - R, 0.0),  # 4 far field front
        (arc_x, arc_y),  # 5 far field, upper split
        (1.0, R),  # 6 far field above TE
        (arc_x, -arc_y),  # 7 far field, lower split
        (1.0, -R),  # 8 far field below TE
        (1 + R, 0.0),  # 9 wake end
        (1 + R, R),  # 10
        (1 + R, -R),  # 11
        (-D0, 0.0),  # 12 layer, leading edge
        surface(XS, 1, True),  # 13 layer, upper split
        (1 + D1 * nu_te[0], D1 * nu_te[1]),  # 14 layer, upper TE
        surface(XS, -1, True),  # 15 layer, lower split
        (1 + D1 * nl_te[0], D1 * nl_te[1]),  # 16 layer, lower TE
        (1 + R, DW),  # 17 layer, upper wake end
        (1 + R, -DW),  # 18 layer, lower wake end
    ]
    verts = [(x, y, 0.0) for x, y in base] + [(x, y, 1.0) for x, y in base]
    o = len(base)

    def grades(x: float) -> tuple[str, str]:
        """Layer and outer expansion ratios on the radial edge at chord position x."""
        g_in = normal_grading(first, ni, layer(x))
        return f"{g_in!r}", f"{normal_grading(first * g_in, no, R)!r}"

    (il, ol), (ix, ox), (it, ot) = grades(0.0), grades(XS), grades(1.0)
    g_inw = normal_grading(1e-3 / k, ni, DW)
    giw, gow = f"{g_inw!r}", f"{normal_grading(1e-3 / k * g_inw, no, R - DW)!r}"
    g_le, g_te, g_wake, g_top = "8", "0.2", "200", "20"

    def e4(a: str, b: str) -> str:
        return f"{a} {b} {b} {a}"

    def hexa(v: tuple[int, int, int, int], cells: tuple[int, int], grading: str) -> str:
        a, b, c, d = v
        return (
            f"    hex ({a} {b} {c} {d} {a + o} {b + o} {c + o} {d + o}) "
            f"({cells[0]} {cells[1]} 1) edgeGrading ({grading} 1 1 1 1)"
        )

    def same(g: str) -> str:
        return f"{g} {g} {g} {g}"

    fs_, fo_ = matched(0.0, XS, float(g_le), nf)  # front: surface, offset
    as_, ao_ = matched(XS, 1.0, float(g_te), na)  # aft
    blocks = [
        # upper side: wall layer, then outer
        hexa((0, 1, 13, 12), (nf, ni), f"{e4(fs_, fo_)} {e4(il, ix)}"),
        hexa((12, 13, 5, 4), (nf, no), f"{e4(fo_, g_le)} {e4(ol, ox)}"),
        hexa((1, 2, 14, 13), (na, ni), f"{e4(as_, ao_)} {e4(ix, it)}"),
        hexa((13, 14, 6, 5), (na, no), f"{e4(ao_, g_te)} {e4(ox, ot)}"),
        hexa((2, 9, 17, 14), (nw, ni), f"{same(g_wake)} {e4(it, giw)}"),
        hexa((14, 17, 10, 6), (nw, no), f"{e4(g_wake, g_top)} {e4(ot, gow)}"),
        # lower side
        hexa((0, 12, 15, 3), (ni, nf), f"{e4(il, ix)} {e4(fs_, fo_)}"),
        hexa((12, 4, 7, 15), (no, nf), f"{e4(ol, ox)} {e4(fo_, g_le)}"),
        hexa((3, 15, 16, 2), (ni, na), f"{e4(ix, it)} {e4(as_, ao_)}"),
        hexa((15, 7, 8, 16), (no, na), f"{e4(ox, ot)} {e4(ao_, g_te)}"),
        hexa((2, 16, 18, 9), (ni, nw), f"{e4(it, giw)} {same(g_wake)}"),
        hexa((16, 8, 11, 18), (no, nw), f"{e4(ot, gow)} {e4(g_wake, g_top)}"),
    ]

    def arc_point(angle_deg: float, z: float) -> str:
        a = math.radians(angle_deg)
        return f"({1 + R * math.cos(a)!r} {R * math.sin(a)!r} {z})"

    edges = []
    for z, f in ((0.0, 0), (1.0, o)):
        for a, b, x0, x1, s in ((0, 1, 0.0, XS, 1), (1, 2, XS, 1.0, 1), (0, 3, 0.0, XS, -1), (3, 2, XS, 1.0, -1)):
            edges.append(f"    spline {a + f} {b + f} ({curve(x0, x1, s, False, z)})")
        for a, b, x0, x1, s in ((12, 13, 0.0, XS, 1), (13, 14, XS, 1.0, 1), (12, 15, 0.0, XS, -1), (15, 16, XS, 1.0, -1)):
            edges.append(f"    spline {a + f} {b + f} ({curve(x0, x1, s, True, z)})")
        edges.append(f"    arc {4 + f} {5 + f} {arc_point((180 + SPLIT_DEG) / 2, z)}")
        edges.append(f"    arc {5 + f} {6 + f} {arc_point((SPLIT_DEG + 90) / 2, z)}")
        edges.append(f"    arc {4 + f} {7 + f} {arc_point(-(180 + SPLIT_DEG) / 2, z)}")
        edges.append(f"    arc {7 + f} {8 + f} {arc_point(-(SPLIT_DEG + 90) / 2, z)}")

    def face(a: int, b: int) -> str:
        return f"            ({a} {b} {b + o} {a + o})"

    airfoil = [face(0, 1), face(1, 2), face(0, 3), face(3, 2)]
    inlet = [face(4, 5), face(5, 6), face(6, 10), face(4, 7), face(7, 8), face(8, 11)]
    outlet = [face(10, 17), face(17, 9), face(9, 18), face(18, 11)]

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
                [
                    patch("airfoil", "wall", airfoil),
                    patch("inlet", "patch", inlet),
                    patch("outlet", "patch", outlet),
                ]
            )
            + "\n);\n",
        ]
    )
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(blocks)} blocks, layer gradings LE/XS/TE {il} {ix} {it}")


if __name__ == "__main__":
    main()
