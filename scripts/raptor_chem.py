"""Raptor 3 main-chamber chemistry inputs for the reacting CFD.

    python scripts/raptor_chem.py OUTDIR

1. Preburner exhaust (full-flow staged combustion): ox-rich O/F 52, fuel-rich O/F 0.225
   (Raptor-like preliminary design, ResearchGate 363367182), equilibrium at the preburner pressure,
   then the turbine removes exactly the pump work. Composition is frozen through the turbine.
2. Skeletal CH4/O2 mechanism: GRI-Mech 3.0 without nitrogen, reduced by DRG on constant-pressure
   reactors at 350 bar sampled over the main-chamber mixture range.
3. NASA-7 thermo refitted 200-1000-6000 K from the NASA-9 database (GRI fits stop at 3500 K and
   OpenFOAM's janafThermo clamps T at Thigh), so the CFD can reach the 3800 K chamber.
4. Validation vs full GRI: equilibrium, ignition delay. Chemkin files for chemkinToFoam.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import warnings

import cantera as ct
import numpy as np

warnings.filterwarnings("ignore", message="NasaPoly2")
PC = 350e5  # chamber pressure
P_PB = 600e5  # preburner pressure (assumed, ~1.7 Pc)
P_PUMP = 700e5  # pump discharge rise (assumed)
ETA_PUMP = 0.75
OF = 3.6
MDOT = 731.0  # kg/s, Pc*At/c* with At from the nozzle study (throat d 0.222 m)
OF_OX_PB, OF_FU_PB = 52.0, 0.225
H_LOX = -12979.0 / 31.9988e-3  # J/kg, O2(L) at 90.17 K (CEA thermo.inp)
H_LCH4 = -89233.0 / 16.0425e-3  # J/kg, CH4(L) at 111.64 K
RHO_LOX, RHO_LCH4 = 1141.0, 422.6
TARGETS = ["CH4", "O2", "CO", "CO2", "H2O", "H2", "OH", "H", "O"]
FUEL_RICH_SPECIES = ["CH4", "O2", "H2O", "CO2", "CO", "H2"]  # kinetically frozen reforming


def base_gas() -> ct.Solution:
    """GRI-3.0 with N and Ar chemistry removed (no nitrogen in a LOX/CH4 engine)."""
    full = ct.Solution("gri30.yaml")
    keep = [s for s in full.species() if "N" not in s.composition and "Ar" not in s.composition]
    names = {s.name for s in keep}
    rx = [r for r in full.reactions() if set(r.reactants) | set(r.products) <= names]
    return ct.Solution(thermo="ideal-gas", kinetics="gas", species=keep, reactions=rx)


def refit_nasa7(sp: ct.Species, nasa9: dict[str, ct.Species]) -> ct.Species:
    """Two-range NASA-7 (200-1000-6000 K) fitted to NASA-9; h and s matched at 298.15/1000 K."""
    src = nasa9.get(sp.name)
    if src is None:
        return sp  # trace intermediate, keep the GRI fit (extrapolated above 3500 K)
    th = src.thermo
    coeffs = [1000.0]
    for lo, hi, tref in ((1000.0, 6000.0, 1000.0), (200.0, 1000.0, 1000.0)):  # h, s continuous at 1000 K
        T = np.linspace(lo, hi, 400)
        w = np.where(np.isclose(T, 1000.0), 200.0, 1.0)  # pin both fits to cp(1000 K): continuous cp
        cp = np.array([th.cp(t) for t in T]) / ct.gas_constant
        tau = T / 1000.0  # scaled so lstsq does not truncate the constant term
        A = np.c_[np.ones_like(T), tau, tau**2, tau**3, tau**4]
        a = np.linalg.lstsq(A * w[:, None], cp * w, rcond=None)[0] / 1000.0 ** np.arange(5)
        h_rt = th.h(tref) / (ct.gas_constant * tref)
        s_r = th.s(tref) / ct.gas_constant
        a6 = tref * (h_rt - (a[0] + a[1] * tref / 2 + a[2] * tref**2 / 3 + a[3] * tref**3 / 4 + a[4] * tref**4 / 5))
        a7 = s_r - (a[0] * np.log(tref) + a[1] * tref + a[2] * tref**2 / 2 + a[3] * tref**3 / 3 + a[4] * tref**4 / 4)
        coeffs += [*a, a6, a7]
    # Cantera order: [Tmid, high(7), low(7)]
    new = ct.Species(sp.name, sp.composition, charge=sp.charge, size=sp.size)
    new.thermo = ct.NasaPoly2(200.0, 6000.0, ct.one_atm, coeffs)
    new.transport = sp.transport
    return new


def with_thermo(gas: ct.Solution, sp_names: list[str] | None = None) -> ct.Solution:
    nasa9 = {s.name: s for s in ct.Species.list_from_file("nasa_gas.yaml")}
    sp_names = sp_names or gas.species_names
    sps = [refit_nasa7(gas.species(n), nasa9) for n in sp_names]
    names = set(sp_names)
    rx = [r for r in gas.reactions() if set(r.reactants) | set(r.products) <= names]
    return ct.Solution(thermo="ideal-gas", kinetics="gas", transport_model="mixture-averaged", species=sps, reactions=rx)


def eq_hp(g: ct.Solution, h: float, P: float, Y=None) -> None:
    """HP equilibrium at an enthalpy the unburned mixture cannot reach (liquid propellants)."""
    g.TP = 1500, P
    if Y is not None:
        g.TPY = 1500, P, Y
    g.equilibrate("TP")
    g.HP = h, P
    g.equilibrate("HP")


def preburners(gas: ct.Solution) -> dict:
    """Mass split so that all LOX and all CH4 pass through a preburner at the quoted O/F."""
    m_ox, m_fu = MDOT * OF / (1 + OF), MDOT / (1 + OF)
    # (m_ox - y)/x = OF_OX_PB, y/(m_fu - x) = OF_FU_PB  ->  x CH4 to OPB, y O2 to FPB
    x = (m_ox - OF_FU_PB * m_fu) / (OF_OX_PB - OF_FU_PB)
    y = OF_FU_PB * (m_fu - x)
    w_ox = P_PUMP / RHO_LOX / ETA_PUMP  # J/kg added by the pump, removed again by the turbine
    w_fu = P_PUMP / RHO_LCH4 / ETA_PUMP
    out = {"split": {"CH4_to_OPB": x, "O2_to_FPB": y}, "pump_work_J_per_kg": {"LOX": w_ox, "CH4": w_fu}}
    for tag, mo, mf, drives in (("OPB", m_ox - y, x, "LOX"), ("FPB", y, m_fu - x, "CH4")):
        m = mo + mf
        h = (mo * (H_LOX + w_ox) + mf * (H_LCH4 + w_fu)) / m
        g = gas if tag == "OPB" else ct.Solution(thermo="ideal-gas", species=[gas.species(s) for s in FUEL_RICH_SPECIES])
        eq_hp(g, h, P_PB, {"O2": mo, "CH4": mf})
        T_pb = g.T
        pump_power = m_ox * w_ox if drives == "LOX" else m_fu * w_fu
        g.HP = h - pump_power / m, PC * 1.15  # turbine exit / injector manifold, frozen composition
        Y = {s: float(v) for s, v in zip(g.species_names, g.Y) if v > 1e-5}
        out[tag] = {
            "mdot": m,
            "OF": mo / mf,
            "T_preburner": T_pb,
            "T_injector": g.T,
            "turbine_power_MW": pump_power / 1e6,
            "MW": g.mean_molecular_weight,
            "Y": Y,
        }
    return out


def chamber_eq(gas: ct.Solution, pb: dict, P: float = PC) -> ct.Solution:
    """Adiabatic equilibrium of the two injector streams mixed at P."""
    Ytot: dict[str, float] = {}
    H = 0.0
    for tag in ("OPB", "FPB"):
        s = pb[tag]
        g = ct.Solution(thermo="ideal-gas", species=[gas.species(n) for n in gas.species_names])
        g.TPY = s["T_injector"], P, s["Y"]
        H += s["mdot"] * g.enthalpy_mass
        for k, v in s["Y"].items():
            Ytot[k] = Ytot.get(k, 0) + s["mdot"] * v
    m = pb["OPB"]["mdot"] + pb["FPB"]["mdot"]
    eq_hp(gas, H / m, P, {k: v / m for k, v in Ytot.items()})
    return gas


def drg(gas: ct.Solution, states: list[tuple[float, float, np.ndarray]], eps: float) -> list[str]:
    nu = gas.product_stoich_coeffs - gas.reactant_stoich_coeffs
    involved = (np.abs(gas.product_stoich_coeffs) + np.abs(gas.reactant_stoich_coeffs)) > 0
    rmax = np.zeros((gas.n_species, gas.n_species))
    for T, P, Y in states:
        gas.TPY = T, P, Y
        Pm = np.abs(nu * gas.net_rates_of_progress)
        den = Pm.sum(1)
        r = (Pm @ involved.T) / np.where(den > 0, den, 1)[:, None]
        rmax = np.maximum(rmax, r)
    keep = {gas.species_index(s) for s in TARGETS}
    stack = list(keep)
    while stack:
        a = stack.pop()
        for b in np.flatnonzero(rmax[a] > eps):
            if b not in keep:
                keep.add(b)
                stack.append(b)
    return [gas.species_names[i] for i in sorted(keep)]


def sample_states(gas: ct.Solution, pb: dict) -> list:
    """Ignition of OPB/FPB gas blends (local O/F 1-20) at 350 bar from 800-1400 K."""
    states = []
    for phi_of in (1.5, 2.5, 3.6, 6.0, 12.0):
        for T0 in (900.0, 1200.0):
            Y = blend(pb, phi_of)
            gas.TPY = T0, PC, Y
            r = ct.IdealGasConstPressureReactor(gas, energy="on")
            net = ct.ReactorNet([r])
            t = 0.0
            while t < 0.02:
                t = net.step()
                states.append((r.T, PC, r.Y.copy()))
    return states


def blend(pb: dict, of_local: float) -> dict[str, float]:
    """Mix OPB and FPB gas so the element O/F (oxidiser mass / fuel mass) equals of_local."""
    f = frac_opb(pb, of_local)
    Y: dict[str, float] = {}
    for tag, w in (("OPB", f), ("FPB", 1 - f)):
        for k, v in pb[tag]["Y"].items():
            Y[k] = Y.get(k, 0) + w * v
    return Y


def ignition_delay(gas: ct.Solution, T0: float, Y: dict, P: float = PC) -> float:
    gas.TPY = T0, P, Y
    r = ct.IdealGasConstPressureReactor(gas)
    net = ct.ReactorNet([r])
    t, Tprev, best, tbest = 0.0, r.T, 0.0, np.nan
    while t < 0.05:
        t = net.step()
        dT = r.T - Tprev
        Tprev = r.T
        if dT > best:
            best, tbest = dT, t
        if r.T > T0 + 1500:
            break
    return tbest


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    base = with_thermo(base_gas())
    pb = preburners(base)
    eq = chamber_eq(base, pb)
    eq_full = {"T": eq.T, "MW": eq.mean_molecular_weight, "gamma": eq.cp / eq.cv,
               "X": {s: float(x) for s, x in zip(eq.species_names, eq.X) if x > 1e-3}}  # fmt: skip
    states = sample_states(base, pb)
    res = {"preburners": pb, "chamber_equilibrium_full": eq_full, "drg": {}}
    for eps in (0.2, 0.4, 0.5, 0.6, 0.8):
        res["drg"][eps] = drg(base, states, eps)
    eps = 0.5  # largest threshold with ignition delay within 6 % of full GRI (0.6 -> 50 %)
    keep = res["drg"][eps]
    red = with_thermo(base, keep)
    eq_r = chamber_eq(red, pb)
    res["chosen_eps"] = eps
    res["reduced"] = {"n_species": red.n_species, "n_reactions": red.n_reactions, "species": red.species_names,
                      "chamber_T": eq_r.T, "chamber_MW": eq_r.mean_molecular_weight}  # fmt: skip
    # ignition-delay validation, stoichiometric-ish blend and the engine O/F
    rows = []
    for of_local in (2.5, 3.6, 6.0):
        Y = blend(pb, of_local)
        for T0 in (900, 1000, 1100, 1250, 1400):
            rows.append([of_local, T0, ignition_delay(base, T0, Y), ignition_delay(red, T0, Y)])
    res["ignition"] = rows
    # flame temperature vs O/F (equilibrium of the two streams at 350 bar)
    sweep = []
    for of_local in np.linspace(1.5, 8, 27):
        for g in (base, red):
            Y = blend(pb, of_local)
            g.TPY = 1000, PC, Y
            hmix = sum(
                w * h
                for w, h in (
                    (frac_opb(pb, of_local), stream_h(g, pb["OPB"])),
                    (1 - frac_opb(pb, of_local), stream_h(g, pb["FPB"])),
                )
            )
            eq_hp(g, hmix, PC, Y)
        sweep.append([float(of_local), base.T, red.T])
    res["Tad_sweep"] = sweep
    red.write_chemkin(out / "chem.inp", thermo_path=out / "therm.dat", transport_path=out / "tran.dat", overwrite=True, quiet=True)  # fmt: skip
    red.write_yaml(out / "raptor_skeletal.yaml")
    write_sutherland(red, out / "transportProperties")
    (out / "chem-results.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({k: res[k] for k in ("preburners", "chamber_equilibrium_full", "reduced")}, indent=1, default=float))
    for e, s in res["drg"].items():
        print("eps", e, len(s))
    for r in rows:
        print("ign O/F %.1f T0 %4d full %.3e red %.3e (%.1f%%)" % (*r, 100 * (r[3] - r[2]) / r[2]))


def write_sutherland(gas: ct.Solution, path: Path) -> None:
    """chemkinToFoam transport dict: Sutherland As, Ts fitted to Cantera's kinetic-theory viscosity.

    mu = As sqrt(T) / (1 + Ts/T)  <=>  sqrt(T)/mu = 1/As + (Ts/As)/T, linear in 1/T over 300-4000 K.
    """
    T = np.linspace(300, 4000, 60)
    mu = []
    for t in T:
        gas.TPX = t, ct.one_atm, "H2O:1"
        mu.append(gas.species_viscosities)
    mu = np.array(mu)
    body = []
    for k, s in enumerate(gas.species_names):
        b, a = np.polyfit(1 / T, np.sqrt(T) / mu[:, k], 1)
        body.append(f'"{s}"\n{{\n    transport\n    {{\n        As {1 / a:.6e};\n        Ts {b / a:.6g};\n    }}\n}}')
    head = "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object transportProperties;\n}\n\n"
    path.write_text(head + "\n".join(body) + "\n", newline="\n")


def frac_opb(pb: dict, of_local: float) -> float:
    o1, f1 = pb["OPB"]["OF"] / (1 + pb["OPB"]["OF"]), 1 / (1 + pb["OPB"]["OF"])
    o2, f2 = pb["FPB"]["OF"] / (1 + pb["FPB"]["OF"]), 1 / (1 + pb["FPB"]["OF"])
    return (of_local * f2 - o2) / ((o1 - o2) - of_local * (f1 - f2))


def stream_h(g: ct.Solution, s: dict) -> float:
    g.TPY = s["T_injector"], PC, s["Y"]
    return g.enthalpy_mass


if __name__ == "__main__":
    main(Path(sys.argv[1]))
