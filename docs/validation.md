# Validation

Every number here comes from a real OpenFOAM run on the development machine (WSL Ubuntu 24.04, ESI OpenFOAM v2412, case dictionaries written by the FoamStudio generator 2.2.0). A FAIL stays a FAIL. Nobody tunes a case until it passes.

| Case | Reference | Quantity | Result | Tolerance | Status |
| --- | --- | --- | --- | --- | --- |
| Lid-driven cavity, Re = 100 | Ghia et al. 1982 | Ux on the vertical centreline, 17 stations | max abs error 0.0121 | 0.05 | **PASS** |
| Backward-facing step, Re_h ≈ 37,000 | Driver and Seegmiller 1985 | Reattachment xr/h | 5.54 / 5.32 | 6.26 ± 0.5 | **FAIL** |
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

Planned next: a 50h run-up and a three-mesh GCI study.

## Nozzle

`samples/nozzle/`: inviscid `rhoCentralFoam`, planar half-nozzle, 400 × 40 cells. The flow chokes and reaches M ≈ 2.2 at the exit. The section averages miss the 1 % band by 1–2 %, and exit total temperature drops 2.5 %, a sign of numerical dissipation. A mesh refinement study is the next step.

## What these results do and do not show

- They show that the generator writes dictionaries that the real solver accepts, and that the full pipeline (generate, mesh, run, sample, compare) works.
- They do **not** certify any turbulence model. The model choice and mesh resolution remain the engineer's responsibility.
