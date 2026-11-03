# Validation

Every number here comes from a real OpenFOAM run on the development machine (WSL Ubuntu 24.04, ESI OpenFOAM v2412, case dictionaries written by the FoamStudio generator 2.2.0; the nozzle uses 2.2.1). A FAIL stays a FAIL. Nobody tunes a case until it passes.

| Case | Reference | Quantity | Result | Tolerance | Status |
| --- | --- | --- | --- | --- | --- |
| Lid-driven cavity, Re = 100 | Ghia et al. 1982 | Ux on the vertical centreline, 17 stations | max abs error 0.0121 | 0.05 | **PASS** |
| Backward-facing step, Re_h ≈ 37,000 | Driver and Seegmiller 1985 | Reattachment xr/h | 10h run-up: 5.54 (FAIL); 50h run-up: **5.90** | 6.26 ± 0.5 | **PASS** (marginal) |
| Convergent-divergent nozzle, A/A* = 2 | 1-D isentropic, γ = 1.4 | Exit Mach, throat p/p0 (section averages) | +1.7 % / −1.9 % | 1 % | **FAIL** |
| ISO 9300 toroidal-throat sonic nozzle, Rc/rt = 4, axisymmetric | Kliegel & Levine (1969) inviscid Cd | Discharge coefficient (3 meshes) | 0.99910 (fine), 0.99911 extrapolated | ±0.1 % | **PASS** (+0.03 %) |
| Same nozzle, Rc/rt = 1 (tight throat) | Kliegel & Levine (1969) | Discharge coefficient | 0.99042 vs 0.98949 | ±0.1 % | **PASS** (+0.09 %) |
| Conical nozzle, 15° half-angle, ε = 4, axisymmetric | 1-D CF × divergence factor λ = (1+cos α)/2 | Thrust coefficient | 1.5287 vs 1.5266 | ±0.5 % | **PASS** (+0.14 %) |
| NACA 0012, α = 0° | Ladson, NASA TM 100526 | Cl / Cd | 0.0000 / 0.00878 | 0 ± 0.05 / 0.008 ± 0.004 | **PASS** (both) |
| NACA 0012, α = 10° | Ladson, NASA TM 100526 | Cl / Cd | 1.073 / 0.0144 | 1.025 ± 0.025 / 0.012 ± 0.008 | Cl **FAIL** (+4.7 %), Cd **PASS** |

## Cavity

`samples/cavity/case.json`: laminar `simpleFoam`, 64 × 64 × 1, 1000 iterations. The solver run took about 6 s.

## Backward-facing step

`samples/backward-facing-step/`: kOmegaSST with wall functions, 23,200 cells, a 10h inlet run-up with a uniform inlet profile, and 4000 iterations. Wall y+ averages 32 (lower) and 29 (upper).

Likely reasons for the short reattachment length:

- The incoming boundary layer is thin, because of the short run-up.
- Only one mesh was run.
- SST tends to under-predict xr/h on this case.

A 50h run-up (28,000 cells) gives xr/h = 5.90 at the sample line nearest the wall, inside the band by 0.14, and 5.64 one millimetre higher. The pass is marginal and comes from one mesh. A three-mesh GCI study is still needed.

### Wall-resolved step (low-Re SST)

`samples/backward-facing-step/case-lowre.json` with a y+ ≈ 1 mesh (54,000 cells, wall y+ avg 0.34) did **not converge** in 6000 iterations (p residual 6e-3). The near-wall Ux changes sign at x/h 0.05, 5.69, 11.7 and 19.1. The extra downstream crossings show the field is not settled, so this run is **inconclusive**. It needs more iterations, or a start from the wall-function solution.

## Nozzle

`samples/nozzle/`: inviscid `rhoCentralFoam`, planar half-nozzle, 400 × 40 cells. The flow chokes and reaches M ≈ 2.2 at the exit. The section averages miss the 1 % band by 1–2 %, and exit total temperature drops 2.5 %, a sign of numerical dissipation. A mesh refinement study is the next step.

## Nozzle, axisymmetric (2026-11-03)

The planar nozzle above fails for a model-form reason: a 2D throat has a curved sonic line, so 1-D theory is the wrong reference. The fix is a reference that is exact for a real 2D throat. Kliegel & Levine (1969) corrected Hall's (1962) transonic series for the inviscid discharge coefficient of an axisymmetric throat with wall curvature R = Rc/rt:

1 − Cd = (γ+1)/(1+R)² · [1/96 − (8γ−27)/(2304(1+R)) + (754γ²−757γ+3633)/(276480(1+R)²)]

Cases are written by `scripts/nozzle_cfd.py` (ISO 9300 toroidal throat, 4° diffuser, air, p0 5 bar, T0 300 K, inviscid, 5° wedge) and run with `rhoCentralFoamAxi`, a patched rhoCentralFoam (`solvers/build_rhoCentralFoamAxi.sh`) that leaves wedge patches out of the Courant sum. Stock rhoCentralFoam counts them and cut dt ~12× at the axis, which is what stopped the earlier axisymmetric attempt. Mass flow is the inlet-patch flux averaged over the last 25 % of each run (the inlet carries a ±0.5 % acoustic oscillation) and scaled to 360° by 2π/sin θ, because the wedge faces are flat triangles, not arcs (2π/θ would bias Cd by 0.13 %).

| Mesh (Rc/rt = 4) | Cells | Cd | vs Kliegel & Levine 0.998812 |
| --- | --- | --- | --- |
| Coarse | 120 × 24 | 0.998215 | −0.060 % |
| Medium | 240 × 48 | 0.999013 | +0.020 % |
| Fine | 480 × 96 | 0.999100 | +0.029 % |
| Richardson extrapolation | | 0.999110 | +0.030 % (observed order 3.2, GCI_fine 0.001 %) |

The converged result sits 0.03 % above the analytic value, inside the third-order truncation of the series. The tight throat (Rc/rt = 1, where the sonic line curves most) gives 0.990420 against 0.989495, +0.09 %. Viscous effects are excluded by design (inviscid on both sides), so this checks the transonic throat physics and the axisymmetric discretisation directly.

**Thrust, 15° conical nozzle (ε = 4, p0 20 bar, back pressure 0.01 bar, 300 × 60 cells).** Thrust is integrated over the exit plane (ρu² + p − pa). The reference is the textbook conical-nozzle model: the 1-D momentum term scaled by the divergence factor λ = (1+cos 15°)/2 = 0.9830 and by the CFD discharge coefficient (0.9944), plus the 1-D pressure term. CFD gives CF = 1.5287 against 1.5266 (+0.14 %). The run started from the 1-D solution (`scripts/nozzle_init.py`) because an impulsive 2000:1 start from rest drove internal energy negative.

## Raptor 3 sea-level nozzle and plume (study, not validation)

There is no public Raptor 3 test data to validate against, so this is an engineering estimate built on the validated nozzle method above.

**Inputs (sourced estimates, not SpaceX data):** chamber pressure 350 bar (Musk, 2023-24), O/F 3.6, expansion ratio 34.34 and exit diameter 1.30 m (FAA Starship Appendix G), so throat diameter 0.222 m. NASA CEA (RocketCEA, equilibrium): Tc 3783 K, throat molar mass 22.95, Pc/Pe 317.5, exit Mach 3.79, sea-level Isp 349 s. The CFD uses one calorically perfect gas with γ = 1.143, chosen so that 1-D theory reproduces CEA's Pc/Pe at ε = 34.34. It then gives c* 1837 m/s (CEA 1854) and 1-D sea-level thrust 253 tf (reported 250-280 tf). Ambient air uses the same gas properties at 300 K and 1 atm, a single-species simplification.

**Geometry and mesh:** 80 % Rao bell (θn 32°, θe 8°, parabolic), 30° convergent, chamber contraction ratio 3, 15 mm lip with still air around the outside of the last 0.8 m of nozzle, plume domain 14 m × 4 m. Axisymmetric 5° wedge, 216,240 cells, inviscid, `rhoCentralFoamAxi`, 8 MPI ranks. The run starts from the 1-D solution inside the nozzle and still air outside (an impulsive start from rest drove internal energy negative in the bell), so the transient is the plume start-up into still air.

**Nozzle performance (t = 12 ms, end of run; nozzle flow established since ~0.5 ms):**

| Quantity | CFD 12 ms | CFD 6.66 ms | 1-D (γ = 1.143) | CEA / reported |
| --- | --- | --- | --- | --- |
| Mass flow (kg/s) | 732.3 (Cd 0.994) | 732.3 | 736.4 | — |
| Sea-level thrust (tf) | 245.7 | 246.8 | 253 | 250-280 reported |
| Vacuum thrust (tf) | 259.3 | 260.5 | — | — |
| Sea-level Isp (s) | 335.5 | 337.0 | 343.7 | 349 (CEA), 350 reported |
| Vacuum Isp (s) | 354.1 | 355.7 | — | — |
| Exit Mach (mass average) | 3.80 | 3.80 | 3.84 | 3.79 |
| Exit pressure (bar, area average) | 1.10 | 1.10 | 1.10 | 1.10 (CEA) |

Thrust moved 0.5 % between 6.66 and 12 ms, and the inlet mass flow spread over the last quarter of the run is 2.2 %, so the nozzle numbers are settled to about ±0.5 %. CFD sits 2.4 % below 1-D Isp: about 0.6 % from the throat Cd and the rest from bell divergence and non-uniform exit flow, typical for an 80 % bell. The remaining gap to CEA (4 %) is mostly the frozen single-γ gas, which cannot recover the shifting-equilibrium energy that CEA includes.

**Plume (12 ms):** the starting shock (the 1 atm pressure disturbance) is at x = 11.8 m and the hot-gas front (T > 500 K) at 11.5 m. Between 6.66 and 12 ms the front advanced about 4 m, roughly 0.75 km/s and slowing. The jet core carries a train of weak shock diamonds: compressions cross the axis at x ≈ 4.9, 6.5, 7.4 and 8.1 m, consistent with a near-ideally expanded jet (pe 1.10 bar vs pa 1.01 bar). The terminal shock (Mach disk) behind the starting vortex ring is at 9.46 m, where M drops from 3.78. It has moved 3.2 m since 6.66 ms, so the plume tip is still a start-up transient: the diamond region upstream of 8 m is quasi-steady, but a fully settled plume needs a longer run or a longer domain. The 14 m outlet was not reached.

**Videos** (4K and 1080p, 0–12 ms, 600 frames, mirrored full nozzle, background coloured at ambient conditions): `raptor3_mach`, `raptor3_velocity`, `raptor3_pressure` (log scale), `raptor3_temperature`, `raptor3_density` (log scale). The earlier `raptor3_plume_4k.mp4` (Mach on the upper half, temperature on the lower half, 0–3 ms) is a preview only.

## Mesh studies (GCI, refinement ratio 2)

| Case | Quantity | Coarse | Medium | Fine | GCI_fine | Reading |
| --- | --- | --- | --- | --- | --- | --- |
| Cavity, 32² / 64² / 128² | min Ux on the vertical centreline | −0.21000 | −0.21305 | −0.21142 | 0.23 % | Oscillatory convergence, so the GCI is indicative only. The fine mesh is 0.0005 from Ghia (−0.21090). |
| Step (50h run-up), 7k / 28k / 112k cells | reattachment xr/h | 5.59 | 5.90 | 6.03 | 10.7 % (±0.64 x/h) | Monotonic convergence toward 6.26, and the fine mesh is inside the band. Caveat: the fine mesh puts wall y+ at 13, in the buffer layer, outside the wall-function range. The coarse mesh is at y+ 66. |
| Nozzle, 100×10 / 200×20 / 400×40 | throat p/p0 (area average) | 0.5144 | 0.5199 | 0.5184 | 0.07 % | Mesh-converged, yet still −1.9 % from 1-D theory. The gap is **model-form** error: a 2D nozzle has a curved sonic line, so it cannot match 1-D isentropic flow to 1 %. |
| NACA 0012 α = 0°, 22k / 90k / 358k cells (generator 2.3.0) | Cd | 0.009356 | 0.008674 | 0.008515 | 0.71 % (±0.00006) | Monotonic, observed order 2.1. Richardson-extrapolated Cd = 0.00847, which is +4.7 % from the NASA TMR SA value (0.00809) and inside Ladson's band. The remaining gap is the 50 c far field (TMR uses ~500 c) and the fixed-velocity far-field boundary. Each run stopped on the Cd/Cl runTimeControl (2743 / 4365 / 1176 iterations); the fine run started from the medium solution via mapFields. |
| Nozzle | exit Mach (mass average) | 2.2227 | 2.2256 | 2.2345 | not defined | The value moves away from 1-D theory as the mesh refines, so it is not in the asymptotic range. |

An axisymmetric wedge version (`samples/nozzle/*-axi`, which matches the 1-D assumptions better) meshes cleanly, but rhoCentralFoam's Courant limit includes the wedge faces. dt drops 12x at the axis, so reaching t = 0.01 s would take hours, and the run was stopped. The nozzle FAIL comes from the reference model, not from the solver or the mesh. A fair check needs a quasi-1-D reference that accounts for the 2D section, or a 2D method-of-characteristics solution.

## NACA 0012

`samples/naca0012/`: a 6-block C-mesh (`nacamesh.py`), 84,000 cells, 50-chord far field, first cell 4e-6 c (y+ avg 0.47). Spalart–Allmaras, Re 6e6, 3000 iterations, p residual about 1e-6.

The first versions of the mesh diverged within 60 iterations, whatever the turbulence model. `checkMesh -allGeometry` traced this to 64 faces at the chordwise block seam with a 180x cell-size jump: the far-field split point sat directly above x = 0.3. Moving the split to 120° fixed it (minimum interpolation weight 0.0056 → 0.17).

**Update (generator 2.2.4, 12-block mesh, 89,600 cells).** The drag excess came from the mesh. The single-layer C-mesh joined the wall to the far field with straight lines, so wall cells were on average 29.8° non-orthogonal (90th percentile 59°). `nacamesh.py` now builds a wall layer from the surface normal offset (0.004 c thick at the LE, 0.02 c at the TE). The offset edges use per-cell multi-grading so that their nodes sit at the same chord x as the surface nodes, because blockMesh spaces nodes by arc length. Wall-cell non-orthogonality dropped to a mean of 4.9° (max 17.6°). Generator 2.2.4 also sets Spalart–Allmaras `nuTilda = 0` on walls instead of 5ν. That fix had no measurable effect on these results (Cd unchanged to 4 digits).

| α | Cl | Cd (pressure + viscous) | NASA TMR SA | Difference |
| --- | --- | --- | --- | --- |
| 0° | 0.0000 | 0.00878 (0.00167 + 0.00712) | Cd 0.00809 | Cd +8.6 % |
| 10° | 1.073 | 0.01445 (0.00824 + 0.00621) | Cl 1.09, Cd 0.0123 | Cl −1.5 %, Cd +17 % |

The α = 10° Cl misses Ladson's experimental band (1.025 ± 0.025) but is within 1.5 % of the SA benchmark. SA itself over-predicts lift at this angle compared with the experiment, so this is model-form error and the case is not retuned. Replacing the cellLimited gradients with unlimited ones (old mesh, α = 10°, restarted from the converged solution) moved Cl 1.118 → 1.071 and left Cd at 0.0205.

**Far-field boundary (generator 2.3.0).** The `freestreamVelocity`/`freestreamPressure` pair on the C arc and the far-field lines did not settle on this mesh. At α = 0°, Cl swung ±0.3 and Cd went negative within 10,000 iterations, with gradient limiting on or off. A fixed-velocity far field converged. So the freestream role still defaults to `inletOutlet`, the freestream pair is opt-in, and the airfoil template uses a fixed-velocity far field.

Earlier result (old mesh, generator 2.2.3), kept for the record: at α = 10°, Cl = 1.118 and Cd = 0.0203. For comparison, NASA TMR's SA solution gives Cl ≈ 1.09 and Cd ≈ 0.0123, so lift is within 2.5 % of the SA benchmark but drag is about 65 % high. Likely causes: fixed-velocity far field on the straight top and bottom boundaries (no freestream/characteristic BC in the generator), and a single mesh. At α = 0°, Cl = 0.0002 (pass) and Cd = 0.0143 against TMR's 0.0081 (about 77 % high). Drag is high by a similar fraction at both angles, which points to one systematic cause rather than anything angle-specific.

## What these results do and do not show

- They show that the generator writes dictionaries that the real solver accepts, and that the full pipeline (generate, mesh, run, sample, compare) works.
- They do **not** certify any turbulence model. The model choice and mesh resolution remain the engineer's responsibility.
