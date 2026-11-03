"""OpenFOAM dictionary writers for physics the case generator does not cover.

Every function returns dictionary text (or entries); `write(case, rel, text)` puts it in the case.
Pure Python, no Qt. Dictionaries are parse-checked against real OpenFOAM in tests/physics_check.sh.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

Vec = tuple[float, float, float]

HEAD = (
    "FoamFile\n{{\n    version     2.0;\n    format      ascii;\n"
    "    class       {cls};\n    object      {obj};\n}}\n\n"
)


def _head(obj: str, cls: str = "dictionary") -> str:
    return HEAD.format(cls=cls, obj=obj)


def _vec(v: Vec) -> str:
    return f"({v[0]:g} {v[1]:g} {v[2]:g})"


def write(case: Path, rel: str, text: str) -> Path:
    path = case / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, newline="\n")
    return path


# ------------------------------------------------------------------ rotating machinery
def mrf(
    zone: str, origin: Vec, axis: Vec, rpm: float, non_rotating: list[str] | None = None
) -> str:
    """constant/MRFProperties: steady rotating frame for a cell zone (pumps, fans, mixers)."""
    nr = " ".join(non_rotating or [])
    return (
        _head("MRFProperties")
        + f"""MRF1
{{
    cellZone    {zone};
    active      yes;
    nonRotatingPatches ({nr});
    origin      {_vec(origin)};
    axis        {_vec(axis)};
    omega       {rpm * 2 * math.pi / 60:.10g};  // {rpm:g} rpm
}}
"""
    )


def solid_body_rotation(zone: str, origin: Vec, axis: Vec, rpm: float) -> str:
    """constant/dynamicMeshDict: sliding-mesh rotor (pair with cyclicAMI interfaces)."""
    return (
        _head("dynamicMeshDict")
        + f"""dynamicFvMesh   dynamicMotionSolverFvMesh;
motionSolverLibs (fvMotionSolvers);
motionSolver    solidBody;
cellZone        {zone};
solidBodyMotionFunction rotatingMotion;
origin          {_vec(origin)};
axis            {_vec(axis)};
omega           {rpm * 2 * math.pi / 60:.10g};  // {rpm:g} rpm
"""
    )


def adaptive_refinement(
    field: str,
    lower: float,
    upper: float,
    max_level: int = 2,
    max_cells: int = 2_000_000,
    every: int = 10,
) -> str:
    """constant/dynamicMeshDict: refine where lower < field < upper (e.g. magGradRho for shocks)."""
    return (
        _head("dynamicMeshDict")
        + f"""dynamicFvMesh   dynamicRefineFvMesh;
refineInterval  {every};
field           {field};
lowerRefineLevel {lower:g};
upperRefineLevel {upper:g};
unrefineLevel   {lower / 10:g};
nBufferLayers   1;
maxRefinement   {max_level};
maxCells        {max_cells};
correctFluxes   ((phi none));
dumpLevel       true;
"""
    )


def cyclic_ami_pair(a: str, b: str, axis: Vec = (0, 0, 1), angle: float = 0.0) -> dict[str, str]:
    """boundary entries: sliding interface (angle 0) or rotationally periodic pair (angle deg)."""

    def entry(nbr: str, ang: float) -> str:
        rot = (
            (
                f" transform rotational; rotationAxis {_vec(axis)}; rotationCentre (0 0 0);"
                f" rotationAngle {ang:g};"
            )
            if angle
            else " transform noOrdering;"
        )
        return f"{{ type cyclicAMI; neighbourPatch {nbr};{rot} }}"

    return {a: entry(b, angle), b: entry(a, -angle)}


def rotating_wall(origin: Vec, axis: Vec, rpm: float) -> str:
    return (
        f"{{\n        type            rotatingWallVelocity;\n        origin          {_vec(origin)};\n"
        f"        axis            {_vec(axis)};\n        omega           {rpm * 2 * math.pi / 60:.10g};\n"
        "        value           uniform (0 0 0);\n    }"
    )


# ------------------------------------------------------------------ boundary condition presets
def isa(h: float) -> tuple[float, float, float, float]:
    """US Standard Atmosphere 1976, 0-86 km geometric altitude: (T K, p Pa, rho kg/m3, a m/s)."""
    r0, g0, M, Rs = 6356766.0, 9.80665, 0.0289644, 8.31432
    hg = r0 * h / (r0 + h) / 1000  # geopotential km
    base = [
        (0, 288.15, -6.5),
        (11, None, 0.0),
        (20, None, 1.0),
        (32, None, 2.8),
        (47, None, 0.0),
        (51, None, -2.8),
        (71, None, -2.0),
        (84.852, None, None),
    ]
    T, p = 288.15, 101325.0
    for (h0, _t, lapse), (h1, _t1, _l1) in zip(base, base[1:], strict=False):
        top = min(hg, h1)
        L = (lapse or 0.0) / 1000
        dh = (top - h0) * 1000
        if L == 0:
            p *= math.exp(-g0 * M * dh / (Rs * T))
        else:
            T1 = T + L * dh
            p *= (T1 / T) ** (-g0 * M / (Rs * L))
            T = T1
        if hg <= h1:
            break
    rho = p * M / (Rs * T)
    return T, p, rho, math.sqrt(1.4 * Rs / M * T)


def preset_entries(kind: str, **kw: float) -> dict[str, str]:
    """Inlet entries for p, T, U. kinds: atmosphere(h, mach), rocket(p0, T0), tunnel(mach, p, T),
    massflow(mdot, T), ramp(p_start, p_end, t_ramp)."""
    if kind == "atmosphere":
        T, p, _rho, a = isa(kw.get("h", 0.0))
        u = kw.get("mach", 0.0) * a
        return {
            "p": f"{{ type freestreamPressure; freestreamValue uniform {p:.8g}; }}",
            "T": f"{{ type inletOutlet; inletValue uniform {T:.6g}; value uniform {T:.6g}; }}",
            "U": f"{{ type freestreamVelocity; freestreamValue uniform ({u:.8g} 0 0); }}",
        }
    if kind == "rocket":
        g = kw.get("gamma", 1.2)
        return {
            "p": f"{{ type totalPressure; p0 uniform {kw['p0']:.8g}; value uniform {kw['p0']:.8g}; }}",
            "T": f"{{ type totalTemperature; gamma {g}; T0 uniform {kw['T0']:.6g}; value uniform {kw['T0']:.6g}; }}",
            "U": "{ type pressureInletOutletVelocity; value uniform (0 0 0); }",
        }
    if kind == "tunnel":
        a = math.sqrt(1.4 * 287.05 * kw["T"])
        return {
            "p": f"{{ type fixedValue; value uniform {kw['p']:.8g}; }}",
            "T": f"{{ type fixedValue; value uniform {kw['T']:.6g}; }}",
            "U": f"{{ type fixedValue; value uniform ({kw['mach'] * a:.8g} 0 0); }}",
        }
    if kind == "massflow":
        return {
            "U": f"{{ type flowRateInletVelocity; massFlowRate {kw['mdot']:.8g}; rhoInlet 1; value uniform (0 0 0); }}",
            "T": f"{{ type fixedValue; value uniform {kw.get('T', 300):.6g}; }}",
            "p": "{ type zeroGradient; }",
        }
    if kind == "ramp":
        return {
            "p": (
                f"{{ type uniformTotalPressure; p0 table ((0 {kw['p_start']:.8g}) "
                f"({kw['t_ramp']:g} {kw['p_end']:.8g})); value uniform {kw['p_start']:.8g}; }}"
            )
        }
    raise ValueError(f"Unknown preset {kind!r}")


def expression_bc(expr: str, field_type: str = "scalar") -> str:
    """exprFixedValue (ESI): e.g. '10*sin(2*pi()*5*time())' or 'pos().x() > 0 ? 1 : 0'."""
    return f"{{\n        type            exprFixedValue;\n        value           uniform {'0' if field_type == 'scalar' else '(0 0 0)'};\n        expression      #{{ {expr} #}};\n    }}"


# ------------------------------------------------------------------ turbulence
RAS = {"kEpsilon", "realizableKE", "kOmegaSST", "SpalartAllmaras", "kOmegaSSTLM", "RNGkEpsilon"}
LES = {"WALE", "dynamicKEqn", "Smagorinsky", "kOmegaSSTDES", "SpalartAllmarasIDDES"}


def turbulence(model: str) -> str:
    """constant/momentumTransport (and turbulenceProperties, same text)."""
    if model == "laminar":
        return _head("momentumTransport") + "simulationType laminar;\n"
    if model in RAS:
        return (
            _head("momentumTransport")
            + f"simulationType RAS;\n\nRAS\n{{\n    model {model};\n    turbulence on;\n    printCoeffs on;\n}}\n"
        )
    if model in LES:
        return _head("momentumTransport") + (
            f"simulationType LES;\n\nLES\n{{\n    model {model};\n    turbulence on;\n    printCoeffs on;\n"
            "    delta cubeRootVol;\n    cubeRootVolCoeffs { deltaCoeff 1; }\n}\n"
        )
    raise ValueError(
        f"Unknown turbulence model {model!r}; choose from {sorted(RAS | LES)} or laminar"
    )


def turbulence_inlet(
    U: float, intensity: float, length: float, nu: float = 1.5e-5
) -> dict[str, float]:
    """k, epsilon, omega, nuTilda from intensity and length scale (Cmu = 0.09)."""
    k = 1.5 * (U * intensity) ** 2
    eps = 0.09**0.75 * k**1.5 / length
    omega = math.sqrt(k) / (0.09**0.25 * length)
    return {
        "k": k,
        "epsilon": eps,
        "omega": omega,
        "nuTilda": math.sqrt(1.5) * U * intensity * length,
        "nut": k / omega if omega else 0.0,
        "nu": nu,
    }


# ------------------------------------------------------------------ named selections / initial fields
def _source(sel: dict[str, Any]) -> str:
    kind = sel["kind"]
    if kind == "box":
        return f"source boxToFace; box {_vec(sel['min'])} {_vec(sel['max'])};"
    if kind == "cylinder":
        return (
            f"source cylinderToFace; p1 {_vec(sel['p1'])}; p2 {_vec(sel['p2'])}; "
            f"radius {sel['radius']:g};"
        )
    if kind == "sphere":
        return f"source sphereToFace; origin {_vec(sel['origin'])}; radius {sel['radius']:g};"
    if kind == "normal":
        return f"source normalToFace; normal {_vec(sel['normal'])}; cos {sel.get('cos', 0.9):g};"
    if kind == "patch":
        return f"source patchToFace; patch {sel['patch']};"
    raise ValueError(f"Unknown selection kind {kind!r}")


def topo_set(selections: list[dict[str, Any]]) -> str:
    """system/topoSetDict: each selection becomes a faceSet; `within` restricts to one patch."""
    actions = []
    for sel in selections:
        actions.append(f"    {{ name {sel['name']}; type faceSet; action new; {_source(sel)} }}")
        if sel.get("within"):
            actions.append(
                f"    {{ name {sel['name']}; type faceSet; action subset; source patchToFace; patch {sel['within']}; }}"
            )
        if sel.get("zone"):
            actions.append(
                f"    {{ name {sel['name']}Zone; type faceZoneSet; action new; source setToFaceZone; faceSet {sel['name']}; }}"
            )
    return _head("topoSetDict") + "actions\n(\n" + "\n".join(actions) + "\n);\n"


def cell_zone_box(name: str, lo: Vec, hi: Vec) -> str:
    """system/topoSetDict for a box cellZone (MRF rotor region, porous zone, ...)."""
    return (
        _head("topoSetDict")
        + f"""actions
(
    {{ name {name}; type cellSet; action new; source boxToCell; box {_vec(lo)} {_vec(hi)}; }}
    {{ name {name}; type cellZoneSet; action new; source setToCellZone; set {name}; }}
);
"""
    )


def create_patch(names: list[str], patch_type: str = "patch") -> str:
    """system/createPatchDict: turn the faceSets from topo_set into patches."""
    ps = "\n".join(
        f"    {{ name {n}; patchInfo {{ type {patch_type}; }} constructFrom set; set {n}; }}"
        for n in names
    )
    return _head("createPatchDict") + f"pointSync false;\n\npatches\n(\n{ps}\n);\n"


def set_fields(defaults: dict[str, str], regions: list[dict[str, Any]]) -> str:
    """system/setFieldsDict. defaults: {'alpha.water': '0'}; regions: {'box': (lo, hi), 'values': {...}}."""
    d = "\n".join(
        f"    volScalarFieldValue {k} {v}" if " " not in v else f"    volVectorFieldValue {k} {v}"
        for k, v in defaults.items()
    )
    rs = []
    for r in regions:
        vals = "\n".join(
            f"            volScalarFieldValue {k} {v}"
            if "(" not in v
            else f"            volVectorFieldValue {k} {v}"
            for k, v in r["values"].items()
        )
        lo, hi = r["box"]
        rs.append(
            f"    boxToCell\n    {{\n        box {_vec(lo)} {_vec(hi)};\n        fieldValues\n        (\n{vals}\n        );\n    }}"
        )
    return (
        _head("setFieldsDict")
        + f"defaultFieldValues\n(\n{d}\n);\n\nregions\n(\n"
        + "\n".join(rs)
        + "\n);\n"
    )


# ------------------------------------------------------------------ meshing
def first_layer(y_plus: float, U: float, L: float, nu: float = 1.5e-5) -> float:
    """Flat-plate estimate of the first-cell height for a target y+ (Schlichting skin friction)."""
    Re = U * L / nu
    cf = (2 * math.log10(Re) - 0.65) ** -2.3
    u_tau = U * math.sqrt(cf / 2)
    return y_plus * nu / u_tau


def layer_controls(n_layers: int, first: float, growth: float, patches: list[str]) -> str:
    """addLayersControls block for snappyHexMeshDict, absolute first-layer thickness."""
    total = first * (growth**n_layers - 1) / (growth - 1)
    ps = "\n".join(f"        {p} {{ nSurfaceLayers {n_layers}; }}" for p in patches)
    return f"""addLayersControls
{{
    relativeSizes       false;
    layers
    {{
{ps}
    }}
    expansionRatio      {growth:g};
    firstLayerThickness {first:.6g};
    thickness           {total:.6g};
    minThickness        {first * 0.3:.6g};
    nGrow               0;
    featureAngle        130;
    nRelaxIter          5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals      3;
    nSmoothThickness    10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle  90;
    nBufferCellsNoExtrude 0;
    nLayerIter          50;
}}
"""


def cfmesh(
    stl: str,
    max_cell: float,
    refinements: dict[str, tuple[float, int]] | None = None,
    layers: int = 0,
) -> str:
    """system/meshDict for cfMesh cartesianMesh (robust hex-dominant mesh from dirty STL)."""
    ref = "\n".join(
        f"    {p} {{ cellSize {s:g}; refinementThickness {s * 4:g}; }}"
        for p, (s, _l) in (refinements or {}).items()
    )
    lay = (
        f"boundaryLayers\n{{\n    nLayers {layers};\n    thicknessRatio 1.2;\n}}\n"
        if layers
        else ""
    )
    return (
        _head("meshDict")
        + f'surfaceFile "{stl}";\nmaxCellSize {max_cell:g};\n\nlocalRefinement\n{{\n{ref}\n}}\n\n{lay}'
    )


# ------------------------------------------------------------------ function objects (post-processing)
def function_objects(names: list[str], wrapped: bool = True, **kw: Any) -> str:
    """Entries for controlDict `functions {}`. Names: schlieren, Q, vorticity, forces, torque,
    pumpHead, probes, yPlus, MachNo, residuals."""
    lib = "libs (fieldFunctionObjects);"
    blocks = {
        "schlieren": f"schlieren {{ type grad; {lib} field rho; result gradRho; writeControl writeTime; }}\n"
        f"    magGradRho {{ type mag; {lib} field gradRho; result magGradRho; writeControl writeTime; }}",
        "Q": f"Q {{ type Q; {lib} writeControl writeTime; }}",
        "vorticity": f"vorticity {{ type vorticity; {lib} writeControl writeTime; }}",
        "yPlus": f"yPlus {{ type yPlus; {lib} writeControl writeTime; }}",
        "MachNo": f"MachNo {{ type MachNo; {lib} writeControl writeTime; }}",
        "residuals": f'residuals {{ type solverInfo; {lib} fields (".*"); }}',
        "forces": (
            f"forces {{ type forces; libs (forces); patches ({' '.join(kw.get('patches', ['wall']))}); "
            f"CofR {_vec(kw.get('origin', (0, 0, 0)))}; rho {kw.get('rho', 'rhoInf')}; rhoInf {kw.get('rhoInf', 1000):g}; "
            "writeControl timeStep; writeInterval 1; }"
        ),
        "pumpHead": (
            f"inletPt {{ type surfaceFieldValue; {lib} regionType patch; name {kw.get('inlet', 'inlet')}; "
            "operation areaAverage; fields (total(p)); writeFields false; writeControl timeStep; }\n"
            f"    outletPt {{ type surfaceFieldValue; {lib} regionType patch; name {kw.get('outlet', 'outlet')}; "
            "operation areaAverage; fields (total(p)); writeFields false; writeControl timeStep; }\n"
            f"    totalP {{ type pressure; {lib} mode total; result total(p); rho rhoInf; rhoInf {kw.get('rhoInf', 1000):g}; }}"
        ),
        "probes": (
            "probes { type probes; libs (sampling); fields (p); probeLocations ("
            + " ".join(_vec(p) for p in kw.get("points", [(0, 0, 0)]))
            + "); writeControl timeStep; }"
        ),
    }
    blocks["torque"] = blocks["forces"]
    unknown = [n for n in names if n not in blocks]
    if unknown:
        raise ValueError(f"Unknown function objects {unknown}")
    body = "\n".join(blocks[n] for n in dict.fromkeys(names))
    if not wrapped:
        return body + "\n"
    return "functions\n{\n    " + body.replace("\n", "\n    ") + "\n}\n"


def include_functions(control_dict: str, name: str = "foamstudioFunctions") -> str:
    """controlDict text with `#include "<name>"` inside its functions block (added once)."""
    import re

    if name in control_dict:
        return control_dict
    line = f'    #include "{name}"\n'
    m = re.search(r"^functions\s*\{[^\n]*\n", control_dict, re.M)
    if m:
        return control_dict[: m.end()] + line + control_dict[m.end() :]
    return control_dict.rstrip() + f"\n\nfunctions\n{{\n{line}}}\n"


# ------------------------------------------------------------------ gases and real fluids
SUTHERLAND = {
    "air": (1.458e-6, 110.4),
    "N2": (1.407e-6, 111.0),
    "O2": (1.693e-6, 127.0),
    "CO2": (1.503e-6, 222.0),
    "H2": (6.362e-7, 72.0),
}
CRITICAL = {
    "O2": (154.58, 5.043e6, 0.022, 31.998),
    "CH4": (190.56, 4.599e6, 0.011, 16.043),
    "H2": (33.19, 1.313e6, -0.216, 2.016),
    "N2": (126.19, 3.396e6, 0.037, 28.013),
    "CO2": (304.13, 7.377e6, 0.225, 44.01),
}


def perfect_gas(molw: float, cp: float, mu: float | str = "air", pr: float = 0.71) -> str:
    """thermophysicalProperties: perfect gas, constant Cp, constant or Sutherland viscosity."""
    if isinstance(mu, str):
        As, Ts = SUTHERLAND[mu]
        transport, coeffs = "sutherland", f"As {As:g}; Ts {Ts:g};"
    else:
        transport, coeffs = "const", f"mu {mu:g}; Pr {pr:g};"
    return (
        _head("thermophysicalProperties")
        + f"""thermoType
{{
    type            hePsiThermo;
    mixture         pureMixture;
    transport       {transport};
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleInternalEnergy;
}}

mixture
{{
    specie         {{ molWeight {molw:g}; }}
    thermodynamics {{ Cp {cp:g}; Hf 0; }}
    transport      {{ {coeffs} }}
}}
"""
    )


def peng_robinson(species: str, cp: float, mu: float, pr: float = 2.0) -> str:
    """thermophysicalProperties for a real fluid near its critical point (LOX, LCH4)."""
    Tc, Pc, omega, W = CRITICAL[species]
    Vc = 0.307 * 8.314 * Tc / Pc  # m3/mol, Peng-Robinson critical compressibility 0.307
    return (
        _head("thermophysicalProperties")
        + f"""thermoType
{{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState PengRobinsonGas;
    specie          specie;
    energy          sensibleEnthalpy;
}}

mixture
{{
    specie         {{ molWeight {W:g}; }}
    equationOfState {{ Tc {Tc:g}; Vc {Vc * 1000:.6g}; Zc 0.307; Pc {Pc:g}; omega {omega:g}; }}
    thermodynamics {{ Cp {cp:g}; Hf 0; }}
    transport      {{ mu {mu:g}; Pr {pr:g}; }}
}}
"""
    )


# ------------------------------------------------------------------ verification helpers
def gci(f1: float, f2: float, f3: float, r: float = 2.0) -> tuple[float, float, float]:
    """Roache GCI, fine first: (observed order, Richardson extrapolation, GCI_fine fraction)."""
    e32, e21 = f3 - f2, f2 - f1
    if e21 == 0 or e32 / e21 <= 0:
        return float("nan"), f1, float("nan")
    p = math.log(abs(e32 / e21)) / math.log(r)
    ext = f1 + (f1 - f2) / (r**p - 1)
    return p, ext, 1.25 * abs((f1 - f2) / f1) / (r**p - 1)


def run_cost(
    cells: int,
    steps: int,
    cores: int,
    us_per_cell_step: float = 2.5,
    price_per_core_hour: float = 0.0,
) -> dict[str, float]:
    """Wall-time estimate from a measured µs/cell-step (FoamStudio measured ~2.2-3.5 on rhoCentralFoam)."""
    core_hours = cells * steps * us_per_cell_step * 1e-6 / 3600
    return {
        "core_hours": core_hours,
        "wall_hours": core_hours / max(cores, 1) / 0.75,
        "cost": core_hours * price_per_core_hour,
    }
