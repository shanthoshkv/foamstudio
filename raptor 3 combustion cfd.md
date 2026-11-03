# Raptor 3 combustion CFD (main chamber + nozzle, reacting RANS)

Status: **in progress, not yet run to convergence.** Setup, chemistry and solver settings are
built and checked; the case starts and integrates without crashing. The production run, the
ignition transient, the plots and the videos are still to do. Handoff prompt for the next machine:
[`RAPTOR3_COMBUSTION_HANDOFF_PROMPT.md`](RAPTOR3_COMBUSTION_HANDOFF_PROMPT.md).

This follows the non-reacting Raptor 3 nozzle/plume study in `docs/validation.md` (section
"Raptor 3 sea-level nozzle and plume"), which used one calorically perfect gas (γ = 1.143) and
`rhoCentralFoamAxi`. This study adds real combustion: two injected gas streams, finite-rate
CH4/O2 chemistry, turbulence-chemistry interaction, and chemistry that keeps reacting through the
nozzle (recombination). There is no public Raptor 3 test data, so this is an engineering estimate,
not a validation.

## 1. Goal and deliverables

- Steady reacting solution of the Raptor 3 main chamber + 80 % bell nozzle (sea level).
- Outputs: chamber pressure from the solution (not imposed), so c* efficiency; thrust and Isp;
  axial profiles of T, p, Mach and species; combustion efficiency (fuel/oxidiser consumed vs x);
  wall heat flux and y+ along the liner; chemistry validation plots.
- Videos: a **close-up of the combustion chamber with combustion taking place** (ignition
  transient: torch-igniter hot spot lights the chamber, flame spreads and anchors on the injector
  rings; temperature + heat release + OH), per-field videos of the full engine, and a **long-form
  narrated video** of the whole study (method, chemistry, mesh, ignition, steady fields, plots,
  performance, limitations). The user asked specifically that the combustion reaction is clearly
  visible in the video.

## 2. Inputs and sources

| Quantity | Value | Source / reasoning |
| --- | --- | --- |
| Cycle | Full-flow staged combustion, gas-gas main injector | public |
| Chamber pressure (target) | 350 bar | Musk 2023-24 (same as the nozzle study) |
| Engine O/F | 3.6 | same as the nozzle study |
| Total mass flow | 731 kg/s (LOX 571.9, CH4 158.9) | Pc·At/c*, At from the nozzle study (throat d 0.222 m), CEA c* 1854 m/s |
| Ox-rich preburner O/F | 52 | "Preliminary design of a Raptor-like engine" (ResearchGate 363367182) |
| Fuel-rich preburner O/F | 0.225 | same paper |
| Preburner pressure | 600 bar | assumed (~1.7 Pc) |
| Pump pressure rise, efficiency | 700 bar, 0.75 | assumed |
| Propellant inlet | O2(L) 90.17 K, h = −12.979 kJ/mol; CH4(L) 111.64 K, h = −89.233 kJ/mol | CEA thermo.inp |
| Hot-gas wall temperature | 800 K, fixed (liner and faceplate) | assumed, regen-cooled copper liner |
| Geometry | `nozzle_cfd.rao_bell(rt, 34.34, rc_ratio 3, conv 30°, θn 32°, θe 8°, 80 %, Lc 0.25 m)` | same contour as the nozzle study; L* ≈ 1.0 m |

Other sources checked (no hard numbers found): Wikipedia SpaceX Raptor and Staged combustion
cycle; Aerojet patents on swirl-coax injector rows; "Numerical analysis of Raptor engine's
combustion chamber" and "Advanced CFD Simulation ... Raptor 2" (ResearchGate, quote a ~3700-3955 K
chamber); Zhukov & Kong skeletal CH4/O2 mechanism (EUCASS 2015) and Liberatori et al. (JPP 2024)
skeletal families, which are the better literature mechanisms for high-pressure CH4/O2 if the
GRI-based one is questioned.

## 3. Preburners and injector gas (`scripts/raptor_chem.py`)

Mass split so all LOX and all CH4 pass through a preburner at the quoted O/F:
CH4 to the ox-rich preburner (OPB) 10.36 kg/s, O2 to the fuel-rich preburner (FPB) 33.42 kg/s.
Each preburner: liquid propellant enthalpy + pump work, HP equilibrium at 600 bar (FPB restricted
to CH4, O2, H2O, CO2, CO, H2 to stand for kinetically frozen fuel-rich gas, no soot). The turbine
then removes exactly the pump power (frozen composition, to 1.15 Pc). Net effect: the injector gas
carries the liquid propellant enthalpy, as CEA assumes.

| Stream | ṁ (kg/s) | T preburner | T injector | Turbine power | Composition (mass) |
| --- | --- | --- | --- | --- | --- |
| Ox-rich (OPB) | 549.02 | 885.6 K | 809.3 K | 46.8 MW | O2 0.9059, H2O 0.0424, CO2 0.0518 |
| Fuel-rich (FPB) | 181.98 | 863.7 K | 809.2 K | 35.1 MW | CH4 0.7633, CO2 0.1323, H2O 0.0932, CO 0.0083, H2 0.0029 |

**Check:** adiabatic equilibrium of the two streams at 350 bar gives **Tc = 3786.8 K, MW 22.69,
γ(frozen) 1.189**, against CEA 3783 K for liquid LOX/CH4 at O/F 3.6 (+0.1 %). Major mole
fractions: H2O 0.515, CO 0.154, CO2 0.154, OH 0.065, H2 0.059, O2 0.029, H 0.014, O 0.009.

## 4. Chemistry

- Base: GRI-Mech 3.0 with all N and Ar chemistry removed (no nitrogen in LOX/CH4): 34 species.
- Reduction: DRG on constant-pressure reactors at 350 bar, OPB/FPB blends at local O/F 1.5-12,
  initial T 900 and 1200 K. Targets CH4, O2, CO, CO2, H2O, H2, OH, H, O.
  Species count vs threshold: eps 0.2/0.4 → 31, **0.5 → 28 (chosen)**, 0.6 → 17, 0.8 → 12.
- Chosen mechanism: **28 species, 175 reactions** (`solvers/raptor3_chem/raptor_skeletal.yaml`,
  Chemkin `chem.inp`). Ignition delay vs full GRI at 350 bar: within 0.6-5.5 % for O/F 2.5, 3.6,
  6.0 and T0 900-1400 K (eps 0.6 jumps to ~50 % error, so 0.5 is the floor). Equilibrium Tad vs
  O/F matches full GRI to 0.1 K over O/F 1.5-8 (peak 3778 K near O/F 3.5).
- Thermo: GRI fits stop at 3500 K and OpenFOAM's `janafThermo::limit` **clamps T at Thigh** (with a
  warning), which would cap the 3790 K flame. All species are refitted to two-range NASA-7,
  200-1000-6000 K, from Cantera's `nasa_gas.yaml`, h and s continuous at 1000 K, fitted in
  τ = T/1000 (an unscaled least-squares fit lost the constant term). Refit error vs source: 1e-9.
  Species missing from `nasa_gas.yaml` (CH2(S), CH2O, C2H2, C2H3, HCCO, CH2CO, CH2CHO, CH3CHO)
  keep their GRI fits; `Allrun.pre` sets every Thigh to 6000.
- Transport: Sutherland As, Ts per species fitted to Cantera kinetic-theory viscosity over
  300-4000 K (within ~3 %), written as `transportProperties` for chemkinToFoam.
- chemkinToFoam quirks fixed in `raptor_comb.py`: strip Cantera `!` header comments; `THERMO` →
  `THERMO ALL`; temperature line right-justified 3F10.0; `REACTIONS CAL/MOLE MOLE` → `REACTIONS`.

### Chemistry solver (important)

0-D chemFoam tests at 350 bar (blend at 1200 K, and chamber equilibrium at 3787 K):

| Solver | Result |
| --- | --- |
| ode seulex, relTol 1e-6 / 1e-2 / 1e-1 | stalls: step collapses to ~5e-9 s even at equilibrium; in the CFD, `step size underflow` then SIGFPE |
| ode Rosenbrock34 | same stall (hung > 10 min on the first CFD iteration) |
| ode Rodas23 | did not start |
| EulerImplicit, equilibriumRateLimiter off | same stall |
| **EulerImplicit, cTauChem 1, equilibriumRateLimiter on** | **~50x faster; end states 3907.0 K (blend) and 3782.8 K (equilibrium) vs 3907.3 / 3782.7 K from the ODE** |

Likely cause: the v2412 standard chemistry Jacobian is approximate for falloff/third-body
reactions, so implicit ODE steps lose stability on the very fast equilibrated reactions at
350 bar. OpenFOAM's own 0-D equilibrium (3782.7 K) matches Cantera (3786.8 K), so the mechanism
and thermo conversion are right.

TDAC (DAC + ISAT) with EulerImplicit **aborts** (`malloc(): invalid size (unsorted)`) on the first
chemistry call, so the case uses `method standard`.

## 5. CFD case (`scripts/raptor_comb.py`)

- Solver: `reactingFoam` (OpenFOAM v2412), local time stepping (`ddtSchemes localEuler`),
  `transonic yes`, hePsiThermo, reactingMixture, janaf + sutherland + perfectGas,
  sensibleEnthalpy, `inertSpecie H2O`. RAS k-ω SST. Combustion: **PaSR (Cmix 1)**, see section 7.
- Mesh: axisymmetric 5° wedge from `nozzle_cfd.write_case` (one blockMesh block per axial station),
  nx 400 × nr 160 = **64,000 cells**, extra axial clustering at the injector face
  (`face_cluster` 4, added to `nozzle_cfd._stations`) and at the throat. checkMesh OK, max
  skewness 0.64. Face x0 = −0.4352 m, chamber radius 0.1921 m, throat radius 0.1109 m at x = 0,
  exit radius 0.65 m at x = 1.6095 m. Domain ends at the nozzle exit (supersonic outlet, no plume).
- Injector face, ring-slot model of a coaxial gas-gas injector: 4 elements, each a centre ox-rich
  annulus (30 % of the ring area), a 3 mm post, a fuel-rich annulus (10 % of the ring area), the rest
  faceplate wall. Radii (m): ox 0-0.0263 / fuel 0.0293-0.0330; ox 0.0608-0.0760 / fuel 0.0790-0.0833;
  ox 0.1089-0.1238 / fuel 0.1268-0.1312; ox 0.1570-0.1717 / fuel 0.1747-0.1793. Patches are split
  after blockMesh with topoSet + createPatch: ox 58 faces, fuel 13, faceplate 89. Fuel annuli are
  only ~3-4 cells wide; refine radially if mixing near the face matters. Gas velocities are about
  100 m/s (ox) and 170 m/s (fuel). Swirl of the real elements is not represented (each swirls about
  its own axis, which an axisymmetric model cannot hold).
- Boundary conditions:
  - ox, fuel: `flowRateInletVelocity` with the full-engine mass flow × wedge share
    (sin 2.5° / π = 0.013884), T fixed 809 K, Y fixed at the stream composition, k at 5 %
    intensity, ω from a 0.5 mm mixing length.
  - wall, faceplate: noSlip, T fixed 800 K, kqR/omega/nutk wall functions,
    `compressible::alphatWallFunction` Prt 0.85.
  - outlet (supersonic exit): zeroGradient p, U, T, Y; inletOutlet for k, ω.
  - **Pc is not imposed**: inlet p is zeroGradient, so chamber pressure comes out of mass flow,
    heat release and the choked throat; Pc vs 350 bar is the c* efficiency check.
- Initial field: 1-D isentropic flow (`scripts/nozzle_init.py`, γ_eff 1.143, Tc 3787 K, p0 350 bar)
  with the uniform chamber equilibrium composition, i.e. the chamber starts burnt and the injected
  809 K gases form the flames. Exit M 3.84.
- `system/fvOptions`: limitTemperature 250-5000 K. PIMPLE: maxCo 0.25, maxDeltaT 1e-4,
  alphaTemp 0.05, alphaY 0.05, rDeltaTSmoothingCoeff 0.025, rDeltaTDampingCoeff 0.5.
- Function objects: mass flow on ox/fuel/outlet, area-average p and T on the faceplate (chamber
  pressure monitor), MachNo, wallHeatFlux on wall + faceplate, yPlus, T/p min-max.
- endTime 8000 LTS iterations, write every 100 (enough frames for a convergence animation).

## 6. Run history on the laptop (2026-11-03)

1. Mesh, patches, chemkinToFoam, initialisation: all OK after the fixes above.
2. EDC + seulex: SIGFPE in seulex at the first chemistry call (step size underflow).
3. EDC + EulerImplicit (rate limiter on), serial, 3 iterations: **ran clean (rc 0, no underflow),
   but ~127 s per iteration serial** (~13 s/iter on 10 ranks, ~18 h for 5000 iterations). The
   log shows EDC integrating chemistry over τ* up to 1.24e-4 s per cell per iteration.
4. EDC + EulerImplicit + TDAC: abort (`malloc(): invalid size`).
5. Switched to **PaSR** (chemistry integrated over the local LTS step, 0.1-3 µs, instead of τ*).
   **Not yet tested**: the 5-iteration timing run was stopped before it ran.

The WSL case on the laptop (`~/foamstudio/nozzles/raptor3-comb`) is not in git; regenerate it.

## 7. Next steps

1. Rebuild the case (`solvers/raptor3_comb_rebuild.ps1`) and time 5 iterations
   (`wsl -- bash solvers/raptor3_comb_smoke.sh 5`) with PaSR. If PaSR is still slow, in order:
   coarser mesh (`-nx 300 -nr 120`), the 17-species mechanism (DRG eps 0.6; ignition error ~50 %,
   acceptable for a mixing-limited gas-gas flame if documented), or EDC with a smaller
   `EDCCoeffs`/fewer cells.
2. Production LTS run on 16 cores (`wsl -- bash solvers/raptor3_comb_run.sh 16`). Converged when
   the faceplate p and outlet mass flow are flat over ~1000 iterations and ṁ_out matches ṁ_in
   within 0.5 %. Watch for T hitting the 5000 K limiter and for inlet backflow.
3. Ignition transient for the close-up video: copy the case, ddt Euler, chamber initial field =
   unburnt OPB/FPB blend at ~350 bar and 809 K (no flame), a torch-igniter hot kernel
   (e.g. ~2500 K, r < 3 cm near the axis just downstream of the faceplate, via setFields),
   inlets as above, chamber + throat only (outlet at a short supersonic extension, or
   `outletMachNumberPressure` like the `chokedNozzle` tutorial), maxCo ~0.5, write every ~5-10 µs
   over ~1-3 ms. Show T, heat release `Qdot` (log scale), OH and CH4/O2.
4. Post-processing script (`scripts/raptor_comb_post.py`, not written yet): Pc, c*, c* efficiency,
   thrust and Isp (sea level and vacuum, exit-plane integral like `nozzle_post.raptor`), combustion
   efficiency vs x, axial profiles, wall heat flux and y+, convergence history, chemistry validation
   plots from `solvers/raptor3_chem/chem-results.json`, contour stills (chamber close-up and full).
5. Videos: chamber close-up (4K and 1080p), full-engine fields, and the narrated long-form video:
   narration with Windows SAPI (`System.Speech`, voice Microsoft Zira) per section, slide/plot
   frames from matplotlib, ffmpeg (libx264 + aac) to stitch.
6. Results into this file, `docs/validation.md` (new "Raptor 3 combustion" section) and the
   website.

## 8. Files

| File | Purpose |
| --- | --- |
| `scripts/raptor_chem.py` | preburners, chamber equilibrium, DRG reduction, NASA-7 refit, Sutherland fit, validation, Chemkin export |
| `scripts/raptor_comb.py` | writes the OpenFOAM case (mesh via `nozzle_cfd`, patches, BCs, thermo, chemistry, controls, `Allrun.pre`) |
| `scripts/nozzle_cfd.py` | contour + blockMesh writer (now with `face_cluster`) |
| `scripts/nozzle_init.py` | 1-D isentropic initial field |
| `scripts/nozzle_post.py` | non-reacting nozzle post-processing (pattern for the reacting post script) |
| `solvers/raptor3_chem/` | generated mechanism (`chem.inp`, `therm.dat`, `transportProperties`, `raptor_skeletal.yaml`, `tran.dat`) and `chem-results.json` |
| `solvers/raptor3_comb_rebuild.ps1` | rebuild + initialise the WSL case |
| `solvers/raptor3_comb_smoke.sh` | serial N-iteration timing test |
| `solvers/raptor3_comb_run.sh` | decompose, parallel run, reconstruct |

Python: Cantera and RocketCEA are in Windows Python 3.12 (`py -3.12`); PyVista is in the repo
`.venv` (3.12). Python 3.9 lacks `Path.write_text(newline=)`, which `nozzle_cfd` uses.

## 9. Known limitations

- Ideal gas at 350 bar: compressibility of the 809 K injector gases is about Z ≈ 1.1, so about 10 %
  density error near the face. Real-gas EoS (Peng-Robinson) is not used.
- GRI-3.0 is validated to ~10 atm; its use at 350 bar is an extrapolation (the skeletal mechanism
  inherits that).
- 2-D axisymmetric ring-slot injector: no element swirl, no discrete element interaction.
- RANS + PaSR: no combustion instability or unsteady flame dynamics in the steady solution.
- Wall functions at high y+ (estimated ~10^3 at the throat), so heat flux is indicative only.
- Fixed 800 K wall: no conjugate heat transfer with the regen channels; no film cooling.
- Preburner pressures and pump numbers are assumptions; only the O/F values are sourced.
