# Validation

Every number here comes from a real OpenFOAM run on the development machine (WSL Ubuntu 24.04, ESI OpenFOAM v2412, case dictionaries written by the FoamStudio generator 2.2.0; the nozzle uses 2.2.1). A FAIL stays a FAIL. Nobody tunes a case until it passes.

| Case | Reference | Quantity | Result | Tolerance | Status |
| --- | --- | --- | --- | --- | --- |
| Lid-driven cavity, Re = 100 | Ghia et al. 1982 | Ux on the vertical centreline, 17 stations | max abs error 0.0121 | 0.05 | **PASS** |
| Backward-facing step, Re_h ≈ 37,000 | Driver and Seegmiller 1985 | Reattachment xr/h | 10h run-up: 5.54 (FAIL); 50h run-up: **5.90** | 6.26 ± 0.5 | **PASS** (marginal) |
| Convergent-divergent nozzle, A/A* = 2 | 1-D isentropic, γ = 1.4 | Exit Mach, throat p/p0 (section averages) | +1.7 % / −1.9 % | 1 % | **FAIL** |
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

## Mesh studies (GCI, refinement ratio 2)

| Case | Quantity | Coarse | Medium | Fine | GCI_fine | Reading |
| --- | --- | --- | --- | --- | --- | --- |
| Cavity, 32² / 64² / 128² | min Ux on the vertical centreline | −0.21000 | −0.21305 | −0.21142 | 0.23 % | Oscillatory convergence, so the GCI is indicative only. The fine mesh is 0.0005 from Ghia (−0.21090). |
| Step (50h run-up), 7k / 28k / 112k cells | reattachment xr/h | 5.59 | 5.90 | 6.03 | 10.7 % (±0.64 x/h) | Monotonic convergence toward 6.26, and the fine mesh is inside the band. Caveat: the fine mesh puts wall y+ at 13, in the buffer layer, outside the wall-function range. The coarse mesh is at y+ 66. |
| Nozzle, 100×10 / 200×20 / 400×40 | throat p/p0 (area average) | 0.5144 | 0.5199 | 0.5184 | 0.07 % | Mesh-converged, yet still −1.9 % from 1-D theory. The gap is **model-form** error: a 2D nozzle has a curved sonic line, so it cannot match 1-D isentropic flow to 1 %. |
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

Earlier result (old mesh, generator 2.2.3), kept for the record: at α = 10°, Cl = 1.118 and Cd = 0.0203. For comparison, NASA TMR's SA solution gives Cl ≈ 1.09 and Cd ≈ 0.0123, so lift is within 2.5 % of the SA benchmark but drag is about 65 % high. Likely causes: fixed-velocity far field on the straight top and bottom boundaries (no freestream/characteristic BC in the generator), and a single mesh. At α = 0°, Cl = 0.0002 (pass) and Cd = 0.0143 against TMR's 0.0081 (about 77 % high). Drag is high by a similar fraction at both angles, which points to one systematic cause rather than anything angle-specific.

## What these results do and do not show

- They show that the generator writes dictionaries that the real solver accepts, and that the full pipeline (generate, mesh, run, sample, compare) works.
- They do **not** certify any turbulence model. The model choice and mesh resolution remain the engineer's responsibility.
