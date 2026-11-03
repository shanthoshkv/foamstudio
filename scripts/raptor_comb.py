"""Raptor 3 main chamber + nozzle, reacting RANS case for reactingFoam (LTS, PaSR, k-omega SST).

    python scripts/raptor_comb.py OUT_ROOT [--nx 400 --nr 160]

Geometry is the nozzle-study contour (nozzle_cfd.rao_bell, same chamber, throat and 80 % bell).
The injector face is a ring-slot model of a coaxial gas-gas injector: N concentric elements,
each an ox-rich-gas annulus (centre post) wrapped by a fuel-rich-gas annulus, with faceplate wall
between elements. Inlets are fixed mass flow at preburner-exhaust composition and temperature
(scripts/raptor_chem.py -> solvers/raptor3_chem/chem-results.json). Pc is NOT imposed: it comes out
of the mass flow, combustion and the choked throat, so Pc vs 350 bar is a c* efficiency check.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import nozzle_cfd as nz  # noqa: E402

CHEM = HERE.parent / "solvers" / "raptor3_chem"
WALL_T = 800.0  # hot-gas-side wall temperature of the regen-cooled liner (assumed)
N_RINGS, OX_FRAC, FU_FRAC, POST = 4, 0.30, 0.10, 0.003
WEDGE_FRAC = math.sin(nz.WEDGE / 2) / math.pi  # wedge share of the full annulus (flat faces)


def contour() -> tuple[np.ndarray, float]:
    eps = 34.34
    rt = 0.65 / math.sqrt(eps)
    c = nz.rao_bell(rt, eps, rc_ratio=3.0, conv_deg=30, theta_n=32, theta_e=8, frac=0.8, Lc=0.25)
    return c, eps


def rings(r_face: float) -> list[tuple[str, float, float]]:
    """(kind, r_in, r_out) for each ox and fuel annulus; each element is centred in its ring."""
    pitch = r_face / N_RINGS
    out = []
    for k in range(N_RINGS):
        a, b = k * pitch, (k + 1) * pitch
        area = math.pi * (b * b - a * a)
        g = 0.0
        for _ in range(20):  # centre the element: equal faceplate land either side
            r0 = a + g
            r1 = math.sqrt(r0 * r0 + OX_FRAC * area / math.pi)
            r2 = r1 + POST
            r3 = math.sqrt(r2 * r2 + FU_FRAC * area / math.pi)
            g = 0.0 if k == 0 else 0.5 * (pitch - (r3 - r0))
        out += [("ox", r0, r1), ("fuel", r2, r3)]
    return out


def H(cls: str, obj: str) -> str:
    return nz._head(cls, obj)


def write(case: Path, rel: str, text: str) -> None:
    (case / rel).parent.mkdir(parents=True, exist_ok=True)
    (case / rel).write_text(text, newline="\n")


def field(name: str, cls: str, dims: str, internal: str, bcs: dict[str, str]) -> str:
    body = "\n".join(f"    {p}\n    {{\n{b}\n    }}" for p, b in bcs.items())
    return (
        H(cls, name)
        + f"dimensions {dims};\ninternalField {internal};\nboundaryField\n{{\n{body}\n"
        "    axis { type empty; }\n    front { type wedge; }\n    back { type wedge; }\n}\n"
    )


def bc(**kw: str) -> str:
    return "\n".join(f"        {k:<16}{v};" for k, v in kw.items())


def build(root: Path, nx: int, nr: int) -> Path:
    import cantera as ct  # noqa: F401  (chem module needs it)
    import raptor_chem as rc

    res = json.loads((CHEM / "chem-results.json").read_text())
    pb = res["preburners"]
    gas = ct.Solution(str(CHEM / "raptor_skeletal.yaml"))
    eq = rc.chamber_eq(gas, pb)
    Y_eq = dict(zip(gas.species_names, eq.Y))
    g_eff = nz.gamma_for_pressure_ratio(34.34, 317.48)
    cont, eps = contour()
    case = nz.Case(
        "raptor3-comb", cont, g_eff, eq.mean_molecular_weight, 350e5, eq.T, 101325,
        nx=nx, nr=nr, face_cluster=4.0,
        notes={"eps": eps, "Pc_target_bar": 350, "OF": 3.6, "mdot": rc.MDOT, "Tc_eq": eq.T,
               "MW_eq": eq.mean_molecular_weight, "wall_T": WALL_T},
    )  # fmt: skip
    d = nz.write_case(case, root)
    shutil.rmtree(d / "0")
    for f in ("constant/turbulenceProperties", "constant/momentumTransport"):
        (d / f).unlink(missing_ok=True)
    (d / "chemkin").mkdir(exist_ok=True)
    for f in ("chem.inp", "therm.dat", "transportProperties"):
        # chemkinToFoam's lexer trips on Cantera's quoted header comments
        # and reads a temperature-range line only after 'THERMO ALL'
        # (right-justified 3F10.0)
        fix = {
            "THERMO": "THERMO ALL",
            "REACTIONS CAL/MOLE MOLE": "REACTIONS",  # lexer wants MOLES; cal/mol + moles are the defaults
            "200.000   1000.000  6000.000": f"{200:10.3f}{1000:10.3f}{6000:10.3f}",
        }
        lines = [fix.get(ln.strip(), ln) for ln in (CHEM / f).read_text().splitlines()]
        write(d, f"chemkin/{f}", "\n".join(ln for ln in lines if not ln.startswith("!")) + "\n")

    x0, r_face = cont[0]
    ring = rings(r_face)
    c = math.cos(nz.WEDGE / 2)
    acts, seen = [], set()
    for kind, r0, r1 in ring:
        acts.append(
            f"    {{ name {kind}; type faceSet; action {'add' if kind in seen else 'new'};"
            f" source boxToFace; box ({x0 - 1e-6} {r0 * c} -1) ({x0 + 1e-6} {r1 * c} 1); }}"
        )
        seen.add(kind)
    acts.append("    { name plate; type faceSet; action new; source patchToFace; patch inlet; }")
    acts.append("    { name plate; type faceSet; action subtract; source faceToFace; sets (ox fuel); }")
    write(d, "system/topoSetDict", H("dictionary", "topoSetDict") + "actions\n(\n" + "\n".join(acts) + "\n);\n")
    write(d, "system/createPatchDict", H("dictionary", "createPatchDict") + """
pointSync false;
patches
(
    { name ox;        patchInfo { type patch; } constructFrom set; set ox; }
    { name fuel;      patchInfo { type patch; } constructFrom set; set fuel; }
    { name faceplate; patchInfo { type wall; }  constructFrom set; set plate; }
);
""")  # fmt: skip

    # ---------------------------------------------------------------- constant
    write(d, "constant/thermophysicalProperties", H("dictionary", "thermophysicalProperties") + """
thermoType
{
    type            hePsiThermo;
    mixture         reactingMixture;
    transport       sutherland;
    thermo          janaf;
    energy          sensibleEnthalpy;
    equationOfState perfectGas;
    specie          specie;
}
inertSpecie         H2O;
chemistryReader     foamChemistryReader;
foamChemistryFile   "<constant>/reactions";
foamChemistryThermoFile "<constant>/thermo.compressibleGas";
""")  # fmt: skip
    write(d, "constant/chemistryProperties", H("dictionary", "chemistryProperties") + """
// ODE solvers (seulex, Rosenbrock34) stall at 350 bar / 3800 K: the step collapses to ~5e-9 s
// even at equilibrium (approximate falloff/third-body Jacobian). EulerImplicit with the
// equilibrium rate limiter reaches the same 0-D end states (chemFoam, within 0.3 K) ~50x faster.
chemistryType { solver EulerImplicit; method standard; }
chemistry       on;
initialChemicalTimeStep 1e-10;
EulerImplicitCoeffs { cTauChem 1; equilibriumRateLimiter on; }
// TDAC (DAC + ISAT) aborts with EulerImplicit in v2412 (malloc: invalid size), so plain chemistry.
""")  # fmt: skip
    write(d, "constant/combustionProperties",
          H("dictionary", "combustionProperties") + "combustionModel PaSR;\nPaSRCoeffs { Cmix 1.0; }\n")  # fmt: skip
    rans = "simulationType RAS;\nRAS { RASModel kOmegaSST; turbulence on; printCoeffs off; }\n"
    write(d, "constant/turbulenceProperties", H("dictionary", "turbulenceProperties") + rans)
    write(d, "constant/g", H("uniformDimensionedVectorField", "g") + "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 0);\n")

    # ---------------------------------------------------------------- boundary conditions
    m_ox = pb["OPB"]["mdot"] * WEDGE_FRAC
    m_fu = pb["FPB"]["mdot"] * WEDGE_FRAC
    walls = ("wall", "faceplate")
    zg = bc(type="zeroGradient")

    def per_patch(ox: str, fuel: str, wall: str, outlet: str) -> dict[str, str]:
        return {"ox": ox, "fuel": fuel, **{w: wall for w in walls}, "outlet": outlet}

    W = lambda n, cls, dims, internal, b: write(d, f"0/{n}", field(n, cls, dims, internal, b))  # noqa: E731
    W("p", "volScalarField", "[1 -1 -2 0 0 0 0]", "uniform 350e5", per_patch(zg, zg, zg, zg))
    W("U", "volVectorField", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)", per_patch(
        bc(type="flowRateInletVelocity", massFlowRate=f"{m_ox:.8g}", rhoInlet="160", value="uniform (0 0 0)"),
        bc(type="flowRateInletVelocity", massFlowRate=f"{m_fu:.8g}", rhoInlet="90", value="uniform (0 0 0)"),
        bc(type="noSlip"), zg))  # fmt: skip
    T_in = bc(type="fixedValue", value=f"uniform {pb['OPB']['T_injector']:.6g}")
    T_fu = bc(type="fixedValue", value=f"uniform {pb['FPB']['T_injector']:.6g}")
    W("T", "volScalarField", "[0 0 0 1 0 0 0]", f"uniform {eq.T:.6g}",
      per_patch(T_in, T_fu, bc(type="fixedValue", value=f"uniform {WALL_T}"), zg))  # fmt: skip
    k_in = bc(type="turbulentIntensityKineticEnergyInlet", intensity="0.05", value="uniform 50")
    W("k", "volScalarField", "[0 2 -2 0 0 0 0]", "uniform 50", per_patch(
        k_in, k_in, bc(type="kqRWallFunction", value="uniform 50"),
        bc(type="inletOutlet", inletValue="uniform 50", value="uniform 50")))  # fmt: skip
    w_in = bc(type="turbulentMixingLengthFrequencyInlet", mixingLength="0.0005", value="uniform 1000")
    W("omega", "volScalarField", "[0 0 -1 0 0 0 0]", "uniform 1000", per_patch(
        w_in, w_in, bc(type="omegaWallFunction", value="uniform 1000"),
        bc(type="inletOutlet", inletValue="uniform 1000", value="uniform 1000")))  # fmt: skip
    calc = bc(type="calculated", value="uniform 0")
    W("nut", "volScalarField", "[0 2 -1 0 0 0 0]", "uniform 0",
      per_patch(calc, calc, bc(type="nutkWallFunction", value="uniform 0"), calc))  # fmt: skip
    W("alphat", "volScalarField", "[1 -1 -1 0 0 0 0]", "uniform 0", per_patch(
        calc, calc, bc(type="compressible::alphatWallFunction", Prt="0.85", value="uniform 0"), calc))  # fmt: skip
    for s in gas.species_names:
        yo, yf = pb["OPB"]["Y"].get(s, 0.0), pb["FPB"]["Y"].get(s, 0.0)
        W(s, "volScalarField", "[0 0 0 0 0 0 0]", f"uniform {Y_eq[s]:.8g}", per_patch(
            bc(type="fixedValue", value=f"uniform {yo:.8g}"), bc(type="fixedValue", value=f"uniform {yf:.8g}"),
            zg, bc(type="inletOutlet", inletValue=f"uniform {Y_eq[s]:.8g}", value=f"uniform {Y_eq[s]:.8g}")))  # fmt: skip
    W("Ydefault", "volScalarField", "[0 0 0 0 0 0 0]", "uniform 0", per_patch(
        bc(type="fixedValue", value="uniform 0"), bc(type="fixedValue", value="uniform 0"), zg,
        bc(type="inletOutlet", inletValue="uniform 0", value="uniform 0")))  # fmt: skip

    # ---------------------------------------------------------------- system
    write(d, "system/controlDict", H("dictionary", "controlDict") + """
application     reactingFoam;
startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         8000;
deltaT          1;
writeControl    timeStep;
writeInterval   100;
purgeWrite      0;
writeFormat     binary;
writePrecision  10;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{
    massFlows
    {
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        writeControl    timeStep;
        writeInterval   10;
        log             false;
        writeFields     false;
        regionType      patch;
        name            ox;
        operation       sum;
        fields          (phi);
    }
    massFuel   { $massFlows; name fuel; }
    massOut    { $massFlows; name outlet; }
    pFace
    {
        $massFlows;
        name            faceplate;
        operation       areaAverage;
        fields          (p T);
    }
    Mach        { type MachNo; libs (fieldFunctionObjects); writeControl writeTime; }
    wallHeatFlux
    {
        type            wallHeatFlux;
        libs            (fieldFunctionObjects);
        patches         (wall faceplate);
        writeControl    writeTime;
    }
    yPlus       { type yPlus; libs (fieldFunctionObjects); writeControl writeTime; }
    Tminmax
    {
        type            fieldMinMax;
        libs            (fieldFunctionObjects);
        fields          (T p);
        writeControl    timeStep;
        writeInterval   10;
        log             false;
    }
}
""")  # fmt: skip
    write(d, "system/fvSchemes", H("dictionary", "fvSchemes") + """
ddtSchemes      { default localEuler; }
gradSchemes     { default Gauss linear; grad(U) cellLimited Gauss linear 1; }
divSchemes
{
    default             none;
    div(phi,U)          Gauss limitedLinearV 1;
    div(phi,Yi_h)       Gauss limitedLinear 1;
    div(phi,K)          Gauss limitedLinear 1;
    div(phid,p)         Gauss limitedLinear 1;
    div(phi,k)          Gauss upwind;
    div(phi,omega)      Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
wallDist        { method meshWave; }
""")  # fmt: skip
    write(d, "system/fvSolution", H("dictionary", "fvSolution") + """
solvers
{
    "rho.*"     { solver diagonal; }
    p           { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.01; }
    pFinal      { $p; relTol 0; }
    "(U|h|k|omega)"      { solver PBiCGStab; preconditioner DILU; tolerance 1e-8; relTol 0.05; }
    "(U|h|k|omega)Final" { $U; }
    Yi          { solver PBiCGStab; preconditioner DILU; tolerance 1e-10; relTol 0.05; }
}
PIMPLE
{
    momentumPredictor   yes;
    transonic           yes;
    nOuterCorrectors    1;
    nCorrectors         2;
    nNonOrthogonalCorrectors 0;
    maxCo               0.25;
    maxDeltaT           1e-4;
    alphaTemp           0.05;
    alphaY              0.05;
    Yref { O2 0.1; CH4 0.1; }
    rDeltaTSmoothingCoeff 0.025;
    rDeltaTDampingCoeff 0.5;
}
relaxationFactors { equations { ".*" 1; } }
""")  # fmt: skip
    write(d, "system/fvOptions", H("dictionary", "fvOptions") + """
limitT
{
    type            limitTemperature;
    active          yes;
    selectionMode   all;
    min             250;
    max             5000;
}
""")  # fmt: skip
    write(d, "system/decomposeParDict", H("dictionary", "decomposeParDict") + "numberOfSubdomains 10;\nmethod scotch;\n")
    write(d, "Allrun.pre", """#!/bin/bash
# Mesh, patches, chemistry conversion. Run inside the case directory.
source /usr/lib/openfoam/openfoam2412/etc/bashrc || true
set -e
blockMesh > log.blockMesh 2>&1
topoSet > log.topoSet 2>&1
createPatch -overwrite > log.createPatch 2>&1
checkMesh > log.checkMesh 2>&1 || true
chemkinToFoam chemkin/chem.inp chemkin/therm.dat chemkin/transportProperties constant/reactions constant/thermo.compressibleGas > log.chemkinToFoam 2>&1
# refitted NASA-7 fits run to 6000 K; janafThermo clamps T at Thigh
sed -i 's/Thigh *[0-9.e+]*;/Thigh           6000;/' constant/thermo.compressibleGas
foamDictionary -entry writeFormat -set ascii system/controlDict > /dev/null  # nozzle_init reads text
postProcess -func writeCellCentres -time 0 > log.cellCentres 2>&1
foamDictionary -entry writeFormat -set binary system/controlDict > /dev/null
""")  # fmt: skip
    meta = json.loads((d / "case-meta.json").read_text())
    meta.update({"rings": ring, "wedge_frac": WEDGE_FRAC, "mdot_ox": pb["OPB"]["mdot"], "mdot_fuel": pb["FPB"]["mdot"],
                 "Y_eq": {k: float(v) for k, v in Y_eq.items() if v > 1e-6}, "species": gas.species_names})  # fmt: skip
    write(d, "case-meta.json", json.dumps(meta, indent=2))
    return d


if __name__ == "__main__":
    a = sys.argv
    nx = int(a[a.index("--nx") + 1]) if "--nx" in a else 400
    nr = int(a[a.index("--nr") + 1]) if "--nr" in a else 160
    p = build(Path(a[1]), nx, nr)
    print(p)
    for r in rings(contour()[0][0, 1]):
        print("%-4s %.4f-%.4f m" % r)
