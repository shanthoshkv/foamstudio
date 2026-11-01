# Validation

Every number here comes from a real OpenFOAM run on the development machine (WSL Ubuntu 24.04, ESI OpenFOAM v2412, case dictionaries written by the FoamStudio generator 2.2.0; the nozzle uses 2.2.1). A FAIL stays a FAIL. Nobody tunes a case until it passes.

| Case | Reference | Quantity | Result | Tolerance | Status |
| --- | --- | --- | --- | --- | --- |
| Lid-driven cavity, Re = 100 | Ghia et al. 1982 | Ux on the vertical centreline, 17 stations | max abs error 0.0121 | 0.05 | **PASS** |
| Backward-facing step, Re_h ≈ 37,000 | Driver and Seegmiller 1985 | Reattachment xr/h | 10h run-up: 5.54 (FAIL); 50h run-up: **5.90** | 6.26 ± 0.5 | **PASS** (marginal) |
| Convergent-divergent nozzle, A/A* = 2 | 1-D isentropic, γ = 1.4 | Exit Mach, throat p/p0 (section averages) | +1.7 % / −1.9 % | 1 % | **FAIL** |
| NACA 0012, α = 0 and 10° | Ladson, NASA TM 100526 | Cl, Cd | not run, needs a C-mesh | see `samples/naca0012/reference.json` | not run |

## Cavity

`samples/cavity/case.json`: laminar `simpleFoam`, 64 × 64 × 1, 1000 iterations. The solver run took about 6 s.

## Backward-facing step

`samples/backward-facing-step/`: kOmegaSST with wall functions, 23,200 cells, a 10h inlet run-up with a uniform inlet profile, and 4000 iterations. Wall y+ averages 32 (lower) and 29 (upper).

Likely reasons for the short reattachment length:

- The incoming boundary layer is thin, because of the short run-up.
- Only one mesh was run.
- SST tends to under-predict xr/h on this case.

A 50h run-up (28,000 cells) gives xr/h = 5.90 at the sample line nearest the wall, inside the band by 0.14, and 5.64 one millimetre higher. The pass is marginal and comes from one mesh. A three-mesh GCI study is still needed.

## Nozzle

`samples/nozzle/`: inviscid `rhoCentralFoam`, planar half-nozzle, 400 × 40 cells. The flow chokes and reaches M ≈ 2.2 at the exit. The section averages miss the 1 % band by 1–2 %, and exit total temperature drops 2.5 %, a sign of numerical dissipation. A mesh refinement study is the next step.

## Mesh studies (GCI, refinement ratio 2)

| Case | Quantity | Coarse | Medium | Fine | GCI_fine | Reading |
| --- | --- | --- | --- | --- | --- | --- |
| Cavity, 32² / 64² / 128² | min Ux on the vertical centreline | −0.21000 | −0.21305 | −0.21142 | 0.23 % | Oscillatory convergence, so the GCI is indicative only. The fine mesh is 0.0005 from Ghia (−0.21090). |
| Step (50h run-up), 7k / 28k / 112k cells | reattachment xr/h | 5.59 | 5.90 | 6.03 | 10.7 % (±0.64 x/h) | Monotonic convergence toward 6.26, and the fine mesh is inside the band. Caveat: the fine mesh puts wall y+ at 13, in the buffer layer, outside the wall-function range. The coarse mesh is at y+ 66. |
| Nozzle, 100×10 / 200×20 / 400×40 | throat p/p0 (area average) | 0.5144 | 0.5199 | 0.5184 | 0.07 % | Mesh-converged, yet still −1.9 % from 1-D theory. The gap is **model-form** error: a 2D nozzle has a curved sonic line, so it cannot match 1-D isentropic flow to 1 %. |
| Nozzle | exit Mach (mass average) | 2.2227 | 2.2256 | 2.2345 | not defined | The value moves away from 1-D theory as the mesh refines, so it is not in the asymptotic range. |

The nozzle FAIL comes from the reference model, not from the solver or the mesh. A fair check needs a quasi-1-D reference that accounts for the 2D section, or a 2D method-of-characteristics solution.

## What these results do and do not show

- They show that the generator writes dictionaries that the real solver accepts, and that the full pipeline (generate, mesh, run, sample, compare) works.
- They do **not** certify any turbulence model. The model choice and mesh resolution remain the engineer's responsibility.
