"""NACA 4-digit C-mesh (12 hex blocks) for blockMesh, and the matching case.json.

Chord 1, leading edge at the origin, far field radius 50 c centred on the trailing edge,
wake to x = 51. Closed trailing edge (-0.1036 coefficient). Patches: airfoil (wall),
inlet (C arc and far-field lines, freestream role), outlet (wake exit), frontAndBack (empty,
z = 0 and 1, so Aref = 1).

A wall layer is built from the surface normal offset (0.004 c thick at the LE, 0.02 c at the
TE), so grid lines leave the wall at right angles. The offset edges use per-cell
multi-grading so their nodes sit at the same chord x as the surface nodes; blockMesh spaces
nodes by arc length. A single-layer C-mesh had wall cells ~30 deg non-orthogonal and drag
~70 % high. `scale` multiplies every cell count (2 = twice as fine each way) for GCI studies.
"""

from __future__ import annotations

import json
import math
from importlib import resources
from typing import Any

R = 50.0  # far field radius
XS = 0.3  # chordwise block split
SPLIT_DEG = 120.0  # far-field point that pairs with the chordwise split
D0, D1 = 0.004, 0.02  # wall layer thickness at the LE and TE (tracks boundary-layer growth)
DW = 0.5  # wall layer half-thickness at the wake exit
N_FRONT, N_AFT, N_IN, N_OUT, N_WAKE = 70, 100, 70, 90, 110

Point = tuple[float, float]


class Naca4:
    def __init__(self, code: str) -> None:
        if len(code) != 4 or not code.isdigit():
            raise ValueError(f"NACA code {code!r} is not 4 digits, for example 0012 or 2412.")
        self.m, self.p, self.t = int(code[0]) / 100, int(code[1]) / 10, int(code[2:]) / 100
        if self.t <= 0 or (self.m > 0 and not 0 < self.p < 1):
            raise ValueError(f"NACA {code}: thickness must be > 0 and camber position 1-9.")

    def half_thickness(self, x: float) -> float:
        return (self.t / 0.2) * (
            0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4
        )

    def camber(self, x: float) -> tuple[float, float]:
        m, p = self.m, self.p
        if m == 0:
            return 0.0, 0.0
        if x < p:
            return m / p**2 * (2 * p * x - x**2), 2 * m / p**2 * (p - x)
        return m / (1 - p) ** 2 * (1 - 2 * p + 2 * p * x - x**2), 2 * m / (1 - p) ** 2 * (p - x)

    def surface(self, x: float, sign: float) -> Point:
        yc, slope = self.camber(x)
        th = math.atan(slope)
        yt = self.half_thickness(x)
        return x - sign * yt * math.sin(th), yc + sign * yt * math.cos(th)

    def normal(self, x: float, sign: float) -> Point:
        """Outward unit normal of the upper (sign 1) or lower (sign -1) surface."""
        h = 1e-7
        a, b = max(x - h, 0.0), min(x + h, 1.0)
        (ax, ay), (bx, by) = self.surface(a, sign), self.surface(b, sign)
        tx, ty = bx - ax, by - ay
        s = math.hypot(tx, ty)
        return (-ty / s, tx / s) if sign > 0 else (ty / s, -tx / s)

    def point(self, x: float, sign: float, off: bool = False) -> Point:
        sx, sy = self.surface(x, sign)
        if not off:
            return sx, sy
        nx, ny = self.normal(x, sign)
        d = D0 + (D1 - D0) * x
        return sx + d * nx, sy + d * ny


def normal_grading(first: float, n: int, length: float) -> float:
    """Total expansion ratio (last/first) of n geometric cells over length with this first cell."""
    lo, hi = 1.000001, 2.0
    r = lo
    for _ in range(200):
        r = (lo + hi) / 2
        if length * (r - 1) / (r**n - 1) > first:
            lo = r
        else:
            hi = r
    return float(r ** (n - 1))


def _arclength(
    foil: Naca4, x0: float, x1: float, sign: float, off: bool
) -> tuple[list[float], list[float]]:
    m = 4000
    xs = [x0 + (x1 - x0) * 0.5 * (1 - math.cos(math.pi * i / m)) for i in range(m + 1)]
    pts = [foil.point(x, sign, off) for x in xs]
    ss = [0.0]
    for (ax, ay), (bx, by) in zip(pts, pts[1:], strict=False):
        ss.append(ss[-1] + math.hypot(bx - ax, by - ay))
    return xs, ss


def _interp(v: float, xs: list[float], ys: list[float]) -> float:
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if xs[mid] <= v else (lo, mid)
    t = (v - xs[lo]) / (xs[hi] - xs[lo])
    return ys[lo] + t * (ys[hi] - ys[lo])


def _matched(
    foil: Naca4, x0: float, x1: float, sign: float, ratio: float, n: int
) -> tuple[str, str]:
    """Multi-gradings for a surface edge and its offset with nodes at the same chord x."""
    r = ratio ** (1 / (n - 1)) if n > 1 else 1.0
    w = [r**i for i in range(n)]
    xs, ss = _arclength(foil, x0, x1, sign, False)
    s_nodes = [ss[-1] * sum(w[:i]) / sum(w) for i in range(n + 1)]
    x_nodes = [_interp(s, ss, xs) for s in s_nodes]
    xo, so = _arclength(foil, x0, x1, sign, True)
    o_nodes = [_interp(x, xo, so) for x in x_nodes]

    def sections(nodes: list[float]) -> str:
        total = nodes[-1] - nodes[0]
        parts = (f"({(b - a) / total!r} 1 1)" for a, b in zip(nodes, nodes[1:], strict=False))
        return "(" + " ".join(parts) + ")"

    return sections(s_nodes), sections(o_nodes)


def c_mesh(code: str = "0012", first: float = 4e-6, scale: float = 1.0) -> str:
    """blockMeshDict text. first: wall cell height in chords (4e-6 gives y+ ~ 0.5 at Re 6e6)."""
    foil = Naca4(code)
    k = scale
    nf, na, ni, no, nw = (max(2, round(n * k)) for n in (N_FRONT, N_AFT, N_IN, N_OUT, N_WAKE))
    first /= k
    split = math.radians(SPLIT_DEG)
    arc_x, arc_y = 1 + R * math.cos(split), R * math.sin(split)
    nu_te, nl_te = foil.normal(1.0, 1), foil.normal(1.0, -1)
    le_u, le_l = foil.normal(1e-6, 1), foil.normal(1e-6, -1)
    le = (le_u[0] + le_l[0], le_u[1] + le_l[1])
    le_n = math.hypot(*le)
    base: list[Point] = [
        (0.0, 0.0),  # 0 leading edge
        foil.point(XS, 1),  # 1 upper split
        (1.0, 0.0),  # 2 trailing edge
        foil.point(XS, -1),  # 3 lower split
        (1 - R, 0.0),  # 4 far field front
        (arc_x, arc_y),  # 5 far field, upper split
        (1.0, R),  # 6 far field above TE
        (arc_x, -arc_y),  # 7 far field, lower split
        (1.0, -R),  # 8 far field below TE
        (1 + R, 0.0),  # 9 wake end
        (1 + R, R),  # 10
        (1 + R, -R),  # 11
        (D0 * le[0] / le_n, D0 * le[1] / le_n),  # 12 layer, leading edge
        foil.point(XS, 1, True),  # 13 layer, upper split
        (1 + D1 * nu_te[0], D1 * nu_te[1]),  # 14 layer, upper TE
        foil.point(XS, -1, True),  # 15 layer, lower split
        (1 + D1 * nl_te[0], D1 * nl_te[1]),  # 16 layer, lower TE
        (1 + R, DW),  # 17 layer, upper wake end
        (1 + R, -DW),  # 18 layer, lower wake end
    ]
    verts = [(x, y, 0.0) for x, y in base] + [(x, y, 1.0) for x, y in base]
    o = len(base)

    def grades(x: float) -> tuple[str, str]:
        g_in = normal_grading(first, ni, D0 + (D1 - D0) * x)
        return f"{g_in!r}", f"{normal_grading(first * g_in, no, R)!r}"

    (il, ol), (ix, ox), (it, ot) = grades(0.0), grades(XS), grades(1.0)
    g_inw = normal_grading(1e-3 / k, ni, DW)
    giw, gow = f"{g_inw!r}", f"{normal_grading(1e-3 / k * g_inw, no, R - DW)!r}"
    g_le, g_te, g_wake, g_top = "8", "0.2", "200", "20"
    fu, fuo = _matched(foil, 0.0, XS, 1, 8.0, nf)
    au, auo = _matched(foil, XS, 1.0, 1, 0.2, na)
    fl, flo = _matched(foil, 0.0, XS, -1, 8.0, nf)
    al, alo = _matched(foil, XS, 1.0, -1, 0.2, na)

    def e4(a: str, b: str) -> str:
        return f"{a} {b} {b} {a}"

    def same(g: str) -> str:
        return f"{g} {g} {g} {g}"

    def hexa(v: tuple[int, int, int, int], cells: tuple[int, int], grading: str) -> str:
        a, b, c, d = v
        return (
            f"    hex ({a} {b} {c} {d} {a + o} {b + o} {c + o} {d + o}) "
            f"({cells[0]} {cells[1]} 1) edgeGrading ({grading} 1 1 1 1)"
        )

    blocks = [
        hexa((0, 1, 13, 12), (nf, ni), f"{e4(fu, fuo)} {e4(il, ix)}"),
        hexa((12, 13, 5, 4), (nf, no), f"{e4(fuo, g_le)} {e4(ol, ox)}"),
        hexa((1, 2, 14, 13), (na, ni), f"{e4(au, auo)} {e4(ix, it)}"),
        hexa((13, 14, 6, 5), (na, no), f"{e4(auo, g_te)} {e4(ox, ot)}"),
        hexa((2, 9, 17, 14), (nw, ni), f"{same(g_wake)} {e4(it, giw)}"),
        hexa((14, 17, 10, 6), (nw, no), f"{e4(g_wake, g_top)} {e4(ot, gow)}"),
        hexa((0, 12, 15, 3), (ni, nf), f"{e4(il, ix)} {e4(fl, flo)}"),
        hexa((12, 4, 7, 15), (no, nf), f"{e4(ol, ox)} {e4(flo, g_le)}"),
        hexa((3, 15, 16, 2), (ni, na), f"{e4(ix, it)} {e4(al, alo)}"),
        hexa((15, 7, 8, 16), (no, na), f"{e4(ox, ot)} {e4(alo, g_te)}"),
        hexa((2, 16, 18, 9), (ni, nw), f"{e4(it, giw)} {same(g_wake)}"),
        hexa((16, 8, 11, 18), (no, nw), f"{e4(ot, gow)} {e4(g_wake, g_top)}"),
    ]

    def curve(x0: float, x1: float, sign: float, off: bool, z: float, n: int = 40) -> str:
        pts = []
        for i in range(1, n):
            x = x0 + (x1 - x0) * 0.5 * (1 - math.cos(math.pi * i / n))
            px, py = foil.point(x, sign, off)
            pts.append(f"({px!r} {py!r} {z})")
        return " ".join(pts)

    def arc_point(angle_deg: float, z: float) -> str:
        a = math.radians(angle_deg)
        return f"({1 + R * math.cos(a)!r} {R * math.sin(a)!r} {z})"

    edges = []
    surf = ((0, 1, 0.0, XS, 1), (1, 2, XS, 1.0, 1), (0, 3, 0.0, XS, -1), (3, 2, XS, 1.0, -1))
    layer = (
        (12, 13, 0.0, XS, 1),
        (13, 14, XS, 1.0, 1),
        (12, 15, 0.0, XS, -1),
        (15, 16, XS, 1.0, -1),
    )
    for z, f in ((0.0, 0), (1.0, o)):
        for offset, rows in ((False, surf), (True, layer)):
            for a, b, x0, x1, s in rows:
                edges.append(f"    spline {a + f} {b + f} ({curve(x0, x1, s, offset, z)})")
        edges.append(f"    arc {4 + f} {5 + f} {arc_point((180 + SPLIT_DEG) / 2, z)}")
        edges.append(f"    arc {5 + f} {6 + f} {arc_point((SPLIT_DEG + 90) / 2, z)}")
        edges.append(f"    arc {4 + f} {7 + f} {arc_point(-(180 + SPLIT_DEG) / 2, z)}")
        edges.append(f"    arc {7 + f} {8 + f} {arc_point(-(SPLIT_DEG + 90) / 2, z)}")

    def face(a: int, b: int) -> str:
        return f"            ({a} {b} {b + o} {a + o})"

    def patch(name: str, kind: str, faces: list[str]) -> str:
        joined = "\n".join(faces)
        return (
            f"    {name}\n    {{\n        type {kind};\n"
            + f"        faces\n        (\n{joined}\n        );\n    }}"
        )

    airfoil = [face(0, 1), face(1, 2), face(0, 3), face(3, 2)]
    inlet = [face(4, 5), face(5, 6), face(6, 10), face(4, 7), face(7, 8), face(8, 11)]
    outlet = [face(10, 17), face(17, 9), face(9, 18), face(18, 11)]
    return "\n".join(
        [
            "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n"
            "    object blockMeshDict;\n}\n",
            f"// NACA {code} C-mesh, scale {scale:g}, first cell {first:g} c (FoamStudio)\n",
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


def airfoil_spec(code: str, alpha_deg: float, reynolds: float) -> dict[str, Any]:
    """case.json for a chord-1, U = 1 Spalart-Allmaras airfoil run (nu = 1/Re, nuTilda = 3 nu)."""
    Naca4(code)
    if reynolds <= 0:
        raise ValueError("The Reynolds number must be positive.")
    text = resources.files("foamstudio.core.mesh").joinpath("airfoil_case.json").read_text("utf-8")
    spec: dict[str, Any] = json.loads(text)
    state = spec["state"]
    a = math.radians(alpha_deg)
    nu = 1.0 / reynolds
    spec["caseName"] = f"naca{code}-a{alpha_deg:g}"
    state["nu"] = nu
    for patch in state["patches"]:
        if patch["role"] == "freestream":
            patch["fields"]["U"].update(Ux=math.cos(a), Uy=math.sin(a), Uz=0)
            patch["fields"]["nuTilda"]["value"] = 3 * nu
    return spec
