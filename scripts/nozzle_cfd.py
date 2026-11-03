"""Axisymmetric nozzle cases for rhoCentralFoamAxi: validation nozzles and a Raptor 3 estimate.

    python scripts/nozzle_cfd.py OUT_ROOT

Writes one OpenFOAM case per entry in CASES under OUT_ROOT (a WSL path seen from Windows,
e.g. \\\\wsl.localhost\\Ubuntu-24.04\\home\\you\\foamstudio\\nozzles). Inviscid (Euler),
calorically perfect gas, 5 deg wedge, mesh written as one blockMesh block per axial station.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

RU = 8314.462618
WEDGE = math.radians(5.0)


# ---------------------------------------------------------------- 1-D gas dynamics
def area_mach(m: float, g: float) -> float:
    return (1 / m) * ((2 / (g + 1)) * (1 + (g - 1) / 2 * m * m)) ** ((g + 1) / (2 * (g - 1)))


def mach_from_area(eps: float, g: float, supersonic: bool = True) -> float:
    lo, hi = (1.0 + 1e-9, 50.0) if supersonic else (1e-6, 1.0 - 1e-9)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if (area_mach(mid, g) > eps) == supersonic:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def p_ratio(m: float, g: float) -> float:  # p/p0
    return (1 + (g - 1) / 2 * m * m) ** (-g / (g - 1))


def cd_kliegel_levine(R: float, g: float) -> float:
    """Inviscid discharge coefficient of an axisymmetric throat, R = Rc/rt (Kliegel & Levine 1969)."""
    a = 1 + R
    return 1 - (g + 1) / a**2 * (
        1 / 96 - (8 * g - 27) / (2304 * a) + (754 * g * g - 757 * g + 3633) / (276480 * a * a)
    )


def mdot_ideal(p0: float, T0: float, At: float, g: float, Rg: float) -> float:
    return At * p0 * math.sqrt(g / (Rg * T0)) * (2 / (g + 1)) ** ((g + 1) / (2 * (g - 1)))


def cf_ideal(eps: float, g: float, pc_pa: float) -> float:
    me = mach_from_area(eps, g)
    pe = p_ratio(me, g)
    mom = math.sqrt(
        2 * g * g / (g - 1) * (2 / (g + 1)) ** ((g + 1) / (g - 1)) * (1 - pe ** ((g - 1) / g))
    )
    return mom + (pe - 1 / pc_pa) * eps


# ---------------------------------------------------------------- contours  r(x), throat at x=0
def arc(xc: float, rc: float, R: float, a0: float, a1: float, n: int = 40) -> np.ndarray:
    t = np.linspace(a0, a1, n)
    return np.c_[xc + R * np.sin(t), rc - R * np.cos(t)]


def toroidal(rt: float, Rc: float, r_in: float, div_deg: float, eps: float) -> np.ndarray:
    """ISO 9300-style: one toroidal arc through the throat, then a straight cone (diffuser)."""
    phi_in = math.acos(1 - (r_in - rt) / Rc)
    th = math.radians(div_deg)
    up = arc(0, rt + Rc, Rc, -phi_in, 0)
    down = arc(0, rt + Rc, Rc, 0, th)[1:]
    x0, r0 = down[-1]
    re = rt * math.sqrt(eps)
    x1 = x0 + (re - r0) / math.tan(th)
    cone = np.c_[np.linspace(x0, x1, 60)[1:], np.linspace(r0, re, 60)[1:]]
    return np.vstack([up, down, cone])


def conical(rt: float, eps: float, conv_deg: float, div_deg: float, r_in: float) -> np.ndarray:
    """Conical nozzle: 1.5 rt upstream arc, 0.5 rt downstream arc, straight cones."""
    tc, td = math.radians(conv_deg), math.radians(div_deg)
    up = arc(0, 2.5 * rt, 1.5 * rt, -tc, 0)
    xa, ra = up[0]
    x_in = xa - (r_in - ra) / math.tan(tc)
    inlet = np.c_[np.linspace(x_in, xa, 40)[:-1], np.linspace(r_in, ra, 40)[:-1]]
    down = arc(0, 1.5 * rt, 0.5 * rt, 0, td)[1:]
    x0, r0 = down[-1]
    re = rt * math.sqrt(eps)
    x1 = x0 + (re - r0) / math.tan(td)
    cone = np.c_[np.linspace(x0, x1, 80)[1:], np.linspace(r0, re, 80)[1:]]
    return np.vstack([inlet, up, down, cone])


def rao_bell(
    rt: float,
    eps: float,
    rc_ratio: float,
    conv_deg: float,
    theta_n: float,
    theta_e: float,
    frac: float,
    Lc: float,
) -> np.ndarray:
    """Chamber cylinder + 30 deg cone + 1.5rt/0.382rt throat arcs + Rao parabolic (Bezier) bell."""
    tc = math.radians(conv_deg)
    r_ch = rt * math.sqrt(rc_ratio)
    up = arc(0, 2.5 * rt, 1.5 * rt, -tc, 0)
    xa, ra = up[0]
    # 0.5*r_ch fillet between chamber wall and cone, kept simple: straight cone to chamber radius
    x_cone0 = xa - (r_ch - ra) / math.tan(tc)
    cone = np.c_[np.linspace(x_cone0, xa, 50)[:-1], np.linspace(r_ch, ra, 50)[:-1]]
    chamber = np.c_[np.linspace(x_cone0 - Lc, x_cone0, 30)[:-1], np.full(29, r_ch)]
    tn, te = math.radians(theta_n), math.radians(theta_e)
    down = arc(0, 1.382 * rt, 0.382 * rt, 0, tn)[1:]
    nx_, ny_ = down[-1]
    re = rt * math.sqrt(eps)
    L = frac * (math.sqrt(eps) - 1) * rt / math.tan(math.radians(15))
    ex, ey = L, re
    # control point: intersection of the tangents at N and E
    m1, m2 = math.tan(tn), math.tan(te)
    qx = (ey - m2 * ex - ny_ + m1 * nx_) / (m1 - m2)
    qy = m1 * (qx - nx_) + ny_
    t = np.linspace(0, 1, 160)[1:]
    bell = np.c_[
        (1 - t) ** 2 * nx_ + 2 * (1 - t) * t * qx + t * t * ex,
        (1 - t) ** 2 * ny_ + 2 * (1 - t) * t * qy + t * t * ey,
    ]
    return np.vstack([chamber, cone, up, down, bell])


# ---------------------------------------------------------------- case description
@dataclass
class Case:
    name: str
    contour: np.ndarray  # wall (x, r), inlet first, exit last
    gamma: float
    molw: float
    p0: float
    T0: float
    p_amb: float
    T_amb: float = 300.0
    nx: int = 200  # axial cells inside the nozzle
    nr: int = 40  # radial cells inside the nozzle
    plume: tuple[float, float] | None = None  # (length past exit, outer radius) in metres
    nx_plume: int = 0
    nr_outer: int = 0
    end_time: float = 3e-3
    write_interval: float = 1e-4
    lip: float = 0.015  # nozzle lip thickness (m)
    n_lip: int = 2
    upstream: float = 0.8  # still-air region wrapped around the nozzle exterior (m)
    ramp: float = 0.0  # seconds to ramp p0 from p_amb (transient start)
    max_co: float = 0.4
    face_cluster: float = 0.0  # extra axial refinement at the inlet (injector) face
    notes: dict[str, object] = field(default_factory=dict)


def _stations(
    contour: np.ndarray, n: int, throat_cluster: float = 3.0, face_cluster: float = 0.0
) -> np.ndarray:
    """n+1 axial stations: cells shrink near the throat (min r) and, optionally, the inlet face."""
    x, r = contour[:, 0], contour[:, 1]
    s = np.linspace(0, 1, 4001)
    xs = x[0] + s * (x[-1] - x[0])
    w = 1 + throat_cluster * np.exp(-(((xs - x[np.argmin(r)]) / (0.6 * r.min())) ** 2))
    w += face_cluster * np.exp(-(xs - x[0]) / (0.5 * r[0]))
    cum = np.concatenate([[0], np.cumsum(0.5 * (w[1:] + w[:-1]) * np.diff(xs))])
    target = np.linspace(0, cum[-1], n + 1)
    xn = np.interp(target, cum, xs)
    return np.c_[xn, np.interp(xn, x, r)]


def _plume_x(x0: float, length: float, n: int, dx0: float) -> np.ndarray:
    """Geometric growth from dx0 at the nozzle exit to fill `length` in n cells."""
    lo, hi = 1.0, 1.2
    for _ in range(200):
        g = 0.5 * (lo + hi)
        total = dx0 * (g**n - 1) / (g - 1) if g != 1 else dx0 * n
        lo, hi = (g, hi) if total < length else (lo, g)
    d = dx0 * g ** np.arange(n)
    d *= length / d.sum()
    return x0 + np.concatenate([[0], np.cumsum(d)])


def write_case(case: Case, root: Path) -> Path:
    d = root / case.name
    for sub in ("system", "constant", "0"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    st = _stations(case.contour, case.nx, face_cluster=case.face_cluster)
    c, s = math.cos(WEDGE / 2), math.sin(WEDGE / 2)
    verts: list[tuple[float, float, float]] = []
    index: dict[tuple, int] = {}

    def v(x: float, r: float, side: int) -> int:
        key = (round(x, 12), round(r, 12), 0 if r == 0 else side)
        if key not in index:
            index[key] = len(verts)
            verts.append((x, r * c, side * r * s))
        return index[key]

    blocks, patches = (
        [],
        {"inlet": [], "wall": [], "outlet": [], "axis": [], "front": [], "back": [], "ambient": []},
    )

    def block(
        x0,
        x1,
        ra0,
        ra1,
        rb0,
        rb1,
        ncr,
        grading="1",
        out_face=None,
        top=None,
        bottom_axis=False,
        left=None,
        bottom=None,
    ):
        # hex: (x0,ra0) (x1,ra1) (x1,rb1) (x0,rb0) on side -1, then side +1
        h = (
            v(x0, ra0, -1),
            v(x1, ra1, -1),
            v(x1, rb1, -1),
            v(x0, rb0, -1),
            v(x0, ra0, 1),
            v(x1, ra1, 1),
            v(x1, rb1, 1),
            v(x0, rb0, 1),
        )
        blocks.append(f"hex ({' '.join(map(str, h))}) (1 {ncr} 1) simpleGrading (1 {grading} 1)")
        patches["back"].append((h[0], h[1], h[2], h[3]))
        patches["front"].append((h[4], h[7], h[6], h[5]))
        if bottom_axis:
            patches["axis"].append((h[0], h[4], h[5], h[1]))
        if bottom:
            patches[bottom].append((h[0], h[4], h[5], h[1]))
        if top:
            patches[top].append((h[3], h[2], h[6], h[7]))
        if left:
            patches[left].append((h[0], h[3], h[7], h[4]))
        if out_face:
            patches[out_face].append((h[1], h[5], h[6], h[2]))

    n = len(st) - 1
    for i in range(n):
        (x0, r0), (x1, r1) = st[i], st[i + 1]
        last = i == n - 1 and case.plume is None
        block(
            x0,
            x1,
            0,
            0,
            r0,
            r1,
            case.nr,
            top="wall",
            bottom_axis=True,
            left="inlet" if i == 0 else None,
            out_face="outlet" if last else None,
        )
    if case.plume:
        length, r_out = case.plume
        xe, re = st[-1]
        dx0 = float(st[-1, 0] - st[-2, 0])
        xs = _plume_x(xe, length, case.nx_plume, dx0)
        # outer radial grading so the first outer cell matches the lip cell size
        dr_lip = re / case.nr
        ratio = max(1.0, (r_out - re) / (case.nr_outer * dr_lip) * 1.0)
        grade = f"{ratio**1.6:.4g}"
        t = case.lip
        # still air around the outside of the nozzle: the lip has real thickness and the
        # ambient inflow sits on far boundaries, not on the lip corner (a singular point)
        up = [k for k in range(n) if st[k, 0] >= xe - case.upstream]
        for k in up:
            (x0, r0), (x1, r1) = st[k], st[k + 1]
            block(
                x0,
                x1,
                r0 + t,
                r1 + t,
                r_out,
                r_out,
                case.nr_outer,
                grading=grade,
                top="ambient",
                bottom="wall",
                left="ambient" if k == up[0] else None,
            )
        for i in range(case.nx_plume):
            last = i == case.nx_plume - 1
            block(
                xs[i],
                xs[i + 1],
                re,
                re,
                re + t,
                re + t,
                case.n_lip,
                left="wall" if i == 0 else None,
                out_face="outlet" if last else None,
            )
            last = i == case.nx_plume - 1
            block(
                xs[i],
                xs[i + 1],
                0,
                0,
                re,
                re,
                case.nr,
                bottom_axis=True,
                out_face="outlet" if last else None,
            )
            block(
                xs[i],
                xs[i + 1],
                re + t,
                re + t,
                r_out,
                r_out,
                case.nr_outer,
                grading=grade,
                top="ambient",
                out_face="outlet" if last else None,
            )
    patch_types = {
        "inlet": "patch",
        "wall": "wall",
        "outlet": "patch",
        "axis": "empty",
        "front": "wedge",
        "back": "wedge",
        "ambient": "patch",
    }
    pt = "\n".join(
        f"    {k}\n    {{\n        type {patch_types[k]};\n        faces\n        (\n"
        + "\n".join(f"            ({' '.join(map(str, f))})" for f in faces)
        + "\n        );\n    }"
        for k, faces in patches.items()
        if faces
    )
    vt = "\n".join(f"    ({x:.10g} {y:.10g} {z:.10g})" for x, y, z in verts)
    (d / "system" / "blockMeshDict").write_text(
        _head("dictionary", "blockMeshDict")
        + "scale 1;\nmergeType points;\n\nvertices\n(\n"
        + vt
        + "\n);\n\nblocks\n(\n    "
        + "\n    ".join(blocks)
        + "\n);\n\nedges ();\n\nboundary\n(\n"
        + pt
        + "\n);\n",
        newline="\n",
    )
    _write_physics(case, d)
    return d


def _head(cls: str, obj: str, loc: str = "") -> str:
    where = f'    location    "{loc}";\n' if loc else ""
    return f"FoamFile\n{{\n    version     2.0;\n    format      ascii;\n    class       {cls};\n{where}    object      {obj};\n}}\n\n"


def _write_physics(case: Case, d: Path) -> None:
    Rg = RU / case.molw
    cp = case.gamma * Rg / (case.gamma - 1)
    W = lambda p, t: (d / p).write_text(t, newline="\n")  # noqa: E731
    W(
        "constant/thermophysicalProperties",
        _head("dictionary", "thermophysicalProperties")
        + f"""
thermoType
{{
    type            hePsiThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleInternalEnergy;
}}

mixture
{{
    specie         {{ molWeight {case.molw}; }}
    thermodynamics {{ Cp {cp:.6g}; Hf 0; }}
    transport      {{ mu 0; Pr 1; }}
}}
""",
    )
    W(
        "constant/turbulenceProperties",
        _head("dictionary", "turbulenceProperties") + "simulationType laminar;\n",
    )
    W(
        "constant/momentumTransport",
        _head("dictionary", "momentumTransport") + "simulationType laminar;\n",
    )
    has_amb = case.plume is not None
    amb_p = (
        f"""    ambient
    {{
        type            totalPressure;
        p0              uniform {case.p_amb};
        value           uniform {case.p_amb};
    }}
"""
        if has_amb
        else ""
    )
    if case.ramp > 0:
        inlet_p = f"""    inlet
    {{
        type            uniformTotalPressure;
        p0              table ((0 {case.p_amb}) ({case.ramp} {case.p0}));
        value           uniform {case.p_amb};
    }}
"""
    else:
        inlet_p = f"""    inlet
    {{
        type            totalPressure;
        p0              uniform {case.p0};
        value           uniform {case.p0};
    }}
"""
    outlet_p = (
        f"""    outlet
    {{
        type            waveTransmissive;
        field           p;
        psi             thermo:psi;
        gamma           {case.gamma};
        fieldInf        {case.p_amb};
        lInf            {0.5 * (case.plume[0] if has_amb else 1)};
        value           uniform {case.p_amb};
    }}
"""
        if has_amb
        else """    outlet
    {
        type            zeroGradient;
    }
"""
    )
    common = """    wall
    {
        type            zeroGradient;
    }
    axis
    {
        type            empty;
    }
    front
    {
        type            wedge;
    }
    back
    {
        type            wedge;
    }
"""
    t_init = case.T_amb if has_amb else case.T0
    p_init = case.p_amb
    W(
        "0/p",
        _head("volScalarField", "p")
        + f"dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform {p_init};\n"
        "boundaryField\n{\n" + inlet_p + outlet_p + amb_p + common + "}\n",
    )
    amb_T = (
        f"""    ambient
    {{
        type            inletOutlet;
        inletValue      uniform {case.T_amb};
        value           uniform {case.T_amb};
    }}
"""
        if has_amb
        else ""
    )
    out_T = (
        (
            f"    outlet\n    {{\n        type inletOutlet;\n        inletValue uniform {case.T_amb};\n"
            f"        value uniform {case.T_amb};\n    }}\n"
        )
        if has_amb
        else "    outlet\n    {\n        type zeroGradient;\n    }\n"
    )
    W(
        "0/T",
        _head("volScalarField", "T")
        + f"dimensions [0 0 0 1 0 0 0];\ninternalField uniform {t_init};\n"
        f"boundaryField\n{{\n    inlet\n    {{\n        type totalTemperature;\n        gamma {case.gamma};\n        T0 uniform {case.T0};\n"
        f"        value uniform {case.T0};\n    }}\n" + out_T + amb_T + common + "}\n",
    )
    amb_U = (
        """    ambient
    {
        type            pressureInletOutletVelocity;
        value           uniform (0 0 0);
    }
"""
        if has_amb
        else ""
    )
    out_U = (
        (
            "    outlet\n    {\n        type inletOutlet;\n        inletValue uniform (0 0 0);\n"
            "        value uniform (0 0 0);\n    }\n"
        )
        if has_amb
        else "    outlet\n    {\n        type zeroGradient;\n    }\n"
    )
    W(
        "0/U",
        _head("volVectorField", "U")
        + "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (0 0 0);\n"
        "boundaryField\n{\n    inlet\n    {\n        type pressureInletOutletVelocity;\n        value uniform (0 0 0);\n    }\n"
        + out_U
        + amb_U
        + common.replace("zeroGradient", "slip", 1)
        + "}\n",
    )
    W(
        "system/fvSchemes",
        _head("dictionary", "fvSchemes")
        + """
fluxScheme      Kurganov;
ddtSchemes      { default Euler; }
gradSchemes     { default Gauss linear; }
divSchemes      { default none; div(tauMC) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes
{
    default         linear;
    reconstruct(rho) vanLeer;
    reconstruct(U)  vanLeerV;
    reconstruct(T)  vanLeer;
}
snGradSchemes   { default corrected; }
""",
    )
    W(
        "system/fvSolution",
        _head("dictionary", "fvSolution")
        + """
solvers
{
    "(rho|rhoU|rhoE)" { solver diagonal; }
    U  { solver smoothSolver; smoother GaussSeidel; nSweeps 2; tolerance 1e-09; relTol 0.01; }
    e  { $U; tolerance 1e-10; relTol 0; }
}
""",
    )
    W(
        "system/controlDict",
        _head("dictionary", "controlDict")
        + f"""
application     rhoCentralFoamAxi;
startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         {case.end_time};
deltaT          1e-10;
writeControl    adjustable;
writeInterval   {case.write_interval};
purgeWrite      0;
writeFormat     binary;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   8;
runTimeModifiable true;
adjustTimeStep  yes;
maxCo           {case.max_co};
maxDeltaT       1;

functions
{{
    flowRates
    {{
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        writeControl    timeStep;
        writeInterval   50;
        log             false;
        writeFields     false;
        regionType      patch;
        name            inlet;
        operation       sum;
        fields          (phi);
    }}
    flowRateOut
    {{
        $flowRates;
        name            outlet;
    }}
}}
""",
    )
    W(
        "system/decomposeParDict",
        _head("dictionary", "decomposeParDict") + "numberOfSubdomains 10;\nmethod scotch;\n",
    )
    rg = RU / case.molw
    meta = {
        "name": case.name,
        "gamma": case.gamma,
        "molw": case.molw,
        "R": rg,
        "p0": case.p0,
        "T0": case.T0,
        "p_amb": case.p_amb,
        "rt": float(case.contour[:, 1].min()),
        "re": float(case.contour[-1, 1]),
        "x_exit": float(case.contour[-1, 0]),
        "wedge_rad": WEDGE,
        **case.notes,
    }
    import json

    W("case-meta.json", json.dumps(meta, indent=2))
    np.savetxt(d / "contour.csv", case.contour, delimiter=",", header="x,r", comments="")


# ---------------------------------------------------------------- the cases
def gamma_for_pressure_ratio(eps: float, pc_pe: float) -> float:
    lo, hi = 1.05, 1.4
    for _ in range(100):
        g = 0.5 * (lo + hi)
        if 1 / p_ratio(mach_from_area(eps, g), g) > pc_pe:  # ratio falls as gamma falls
            hi = g
        else:
            lo = g
    return 0.5 * (lo + hi)


def cases() -> list[Case]:
    rt = 0.01
    out = []
    # V1: ISO 9300 toroidal-throat sonic nozzle, Rc/rt = 4, 4 deg diffuser; three meshes for GCI
    geo = toroidal(rt, 4 * rt, 1.8 * rt, 4.0, 1.5)
    for tag, nx, nr in (("coarse", 120, 24), ("medium", 240, 48), ("fine", 480, 96)):
        out.append(
            Case(
                f"iso9300-R4-{tag}",
                geo,
                1.4,
                28.9647,
                5e5,
                300,
                1e5,
                nx=nx,
                nr=nr,
                end_time=3e-3,
                write_interval=5e-4,
                notes={"Rc_over_rt": 4, "reference": "Kliegel & Levine 1969 inviscid Cd"},
            )
        )
    # V1b: tight throat, Rc/rt = 1, where the curved sonic line matters most
    out.append(
        Case(
            "iso9300-R1-medium",
            toroidal(rt, 1 * rt, 1.8 * rt, 4.0, 1.5),
            1.4,
            28.9647,
            5e5,
            300,
            1e5,
            nx=240,
            nr=48,
            end_time=3e-3,
            write_interval=5e-4,
            notes={"Rc_over_rt": 1, "reference": "Kliegel & Levine 1969 inviscid Cd"},
        )
    )
    # V2: 15 deg conical nozzle, eps 4: thrust vs ideal 1-D x divergence factor
    out.append(
        Case(
            "conical15-eps4-medium",
            conical(rt, 4.0, 30, 15, 2 * rt),
            1.4,
            28.9647,
            2e6,
            300,
            1e3,
            nx=300,
            nr=60,
            end_time=3e-3,
            write_interval=5e-4,
            notes={"div_deg": 15, "eps": 4, "reference": "1-D ideal CF x (1+cos a)/2"},
        )
    )
    # R3: Raptor 3 sea-level estimate. CEA (RocketCEA): Pc 350 bar, O/F 3.6, eps 34.34, Tc 3783 K,
    # throat MW 22.95; gamma chosen so 1-D Pc/Pe matches CEA's 317.5.
    eps = 34.34
    g = gamma_for_pressure_ratio(eps, 317.48)
    rt_r = 0.65 / math.sqrt(eps)
    raptor = rao_bell(
        rt_r, eps, rc_ratio=3.0, conv_deg=30, theta_n=32, theta_e=8, frac=0.8, Lc=0.25
    )
    out.append(
        Case(
            "raptor3-sl",
            raptor,
            g,
            22.95,
            350e5,
            3782.7,
            101325,
            nx=320,
            nr=100,
            plume=(14.0, 4.0),
            nx_plume=700,
            nr_outer=140,
            end_time=0.012,
            write_interval=2e-5,
            ramp=0.0,
            max_co=0.35,
            notes={
                "eps": eps,
                "Pc_bar": 350,
                "OF": 3.6,
                "cea_pc_pe": 317.48,
                "cea_isp_sl_s": 349.4,
                "cea_mach_exit": 3.79,
                "gamma_effective": g,
                "sources": "Pc 350 bar (Musk, 2023-24), eps 34.34 and exit 1.30 m (FAA Appendix G)",
            },
        )
    )
    return out


if __name__ == "__main__":
    root = Path(sys.argv[1])
    want = set(sys.argv[2:])
    for c in cases():
        if want and c.name not in want:
            continue
        p = write_case(c, root)
        print(f"{c.name}: {p}  gamma={c.gamma:.4f}")
