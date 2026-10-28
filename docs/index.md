# FoamStudio

FoamStudio is a desktop GUI for an OpenFOAM workflow. It detects a runtime and runs it as an external process. The HTML file `openfoam_case_generator.html` is the only writer of solver dictionaries.

OpenFOAM is not bundled and is not linked. FoamStudio is GPL-3.0-only.

## What is in 0.9.0

- Import STL, OBJ, Gmsh 2.2 and 4.1, Fluent `.msh` (through meshio), STEP (through the `gmsh` executable), and an OpenFOAM `constant/polyMesh`.
- Build `blockMeshDict` for a box, a channel, or a wedge, and `snappyHexMeshDict` with a flat-plate first-cell height.
- Queue Allrun steps, including `./Allrun` for the existing 225-case matrix, and cancel with a process-tree kill.
- Read residuals, fields, turboForces rows, and write an HTML report plus a ParaView `.foam` state.
- SSH through the system `ssh` client, with SLURM and PBS script text.

GitHub Actions run [40618797616](https://github.com/shanthoshkv/foamstudio/actions/runs/40618797616) passed. Version 1.0 still needs signed installers and the fresh-machine timing test. Those were not executed for this tree.

## Start

```text
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\foamstudio
```

Use regular CPython 3.11 or newer. The free-threaded build has no PySide6 wheel.
