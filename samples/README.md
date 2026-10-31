# Validation samples

Each folder has `reference.json`. Those numbers are the published reference.

| Sample | Check |
| --- | --- |
| `cavity` | Ghia Re=100 vertical-centerline u, absolute tolerance 0.05 |
| `backward-facing-step` | Driver and Seegmiller reattachment length 6.26, tolerance 0.5 |
| `naca0012` | Ladson Cl and Cd at 0° and 10° |
| `nozzle` | Isentropic Mach at A/A*=2 and p/p0 at Mach 1 |

`tests/test_post_report.py` compares values inside and outside those tolerances and writes an HTML report for the cavity, the step, and the aerofoil.

On 2026-10-30 the cavity was run on this machine. `samples/cavity/case.json` is the generator spec (`simpleFoam`, laminar, `nu` 0.01, lid `translatingWallVelocity` with U = (1 0 0)). FoamStudio wrote the dictionaries, then `block_mesh_dict("box", cells=(64, 64, 1), width=0.1)` wrote the mesh. WSL ESI v2412 ran `bash ./Allrun`. `log.checkMesh` says `Mesh OK.` `log.simpleFoam` ends with `End` at time 1000 (execution about 6 s, clock about 14 s). `blockMesh` warned that `convertToMeters` is older than `scale`, and the mesh still built. The centerline sample is `postProcessing/sampleDict/1000/vertical_U.xy`. ESI v2412 rejected sample type `lineUniform`; the dict that worked uses type `uniform`. Interpolating Ux onto the Ghia stations and calling `compare_series` passed. The largest absolute error was 0.0121, at y = 0.7344. The step, the aerofoil, and the nozzle have no solver comparison yet.

On 2026-10-31 the backward-facing step was run: `samples/backward-facing-step/case.json` (`simpleFoam`, kOmegaSST, wall functions, U 44.2 m/s, h 12.7 mm, nu 1.5e-5, Re_h about 37,000) plus the hand-written 3-block `blockMeshDict` (23,200 cells, 10h inlet, 30h outlet, expansion 1.125) and `sampleDict`. `Mesh OK.`, 4000 iterations, final residuals about 1e-5, wall y+ avg 32 / 29. Ux sampled at y = -h + 0.3 mm and + 1.0 mm above the floor changes sign at xr/h = **5.54** and **5.32**. Reference is 6.26 ± 0.5, so this run **does not pass** (about 0.2 short of the lower bound). One mesh, one model, uniform inlet profile with only a 10h run-up (thin boundary layer). No sensitivity study was done, and the reference was not adjusted.


On 2026-10-31 the nozzle was run: `samples/nozzle/case.json` (`rhoCentralFoam`, inviscid: slip wall, symmetry plane; inlet totalPressure 1 bar / totalTemperature 300 K; outlet `waveTransmissive` back pressure 5 kPa) on the planar `blockMeshDict` (A/A* = 1 + (x/0.5)^2, 400 x 40 cells), 0.01 s (~14k steps, a few minutes). The flow choked and went supersonic. Centreline: exit M 2.225, throat p/p0 0.426 (2D sonic line is curved, so the centreline is the wrong comparison). Section averages from `sampleCross`: throat mass-averaged M 1.023, area-averaged p/p0 0.518 (-1.9 %); exit M 2.235 (+1.7 %), p/p0 0.096 (+2.3 %). Reference tolerance is 1 %, so this **does not pass**. Exit total temperature 292.5 K vs 300 K shows numerical dissipation. One mesh, no refinement study.

NACA 0012 was not run. The ESI tutorial blockMesh stretched to a 50-chord domain with y+ ~1 grading failed `checkMesh` (zero-area faces, non-orthogonality 90, aspect ratio 7.7e5). It needs a purpose-built C-mesh.

On 2026-10-31 the step was rerun with a **50h run-up** (`blockMeshDict-50h`, 28,000 cells, same spec, 4000 iterations, about 271 s of solver time). Reattachment xr/h is **5.90** at y = -h + 0.3 mm (the sample line nearest the wall) and 5.64 at -h + 1.0 mm. Against 6.26 ± 0.5 the near-wall value **passes** (margin 0.14), and the 1 mm line is just outside. The longer run-up moved xr/h by +0.36, which supports the thin-inlet-boundary-layer explanation. The pass is marginal: one mesh, no GCI, and wall y+ averages 29 / 27 (the Allrun check flags both walls just below 30).
