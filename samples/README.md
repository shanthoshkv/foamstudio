# Validation samples

Each folder has `reference.json`. The numbers are the published reference, not a solver result from this machine.

| Sample | Check |
| --- | --- |
| `cavity` | Ghia Re=100 vertical-centerline u, absolute tolerance 0.05 |
| `backward-facing-step` | Driver and Seegmiller reattachment length 6.26, tolerance 0.5 |
| `naca0012` | Ladson Cl and Cd at 0° and 10° |
| `nozzle` | Isentropic Mach at A/A*=2 and p/p0 at Mach 1 |

`tests/test_post_report.py` compares values inside and outside those tolerances and writes an HTML report for the cavity, the step, and the aerofoil. A real OpenFOAM run of these cases was not executed here.
