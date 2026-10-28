# User guide

## Project

File → New project... creates `foamstudio.json`, `case/`, and `geometry/`. File → Write case runs the HTML generator. Python does not write the 25 solver dictionaries.

## Geometry

File → Import geometry... reads a surface into the centre view. The patch list is in the properties dock. A picked patch is the first row passed to the generator when the generator view is open. Headless mode keeps the generator closed.

The centre label stays "No geometry loaded." until an import succeeds. Clicking Geometry, Mesh, Setup, Run, Results, or Reports changes the properties dock.

PyVista draws the surface only when `FOAMSTUDIO_VIEWER=1` and a display can host the widget. Offscreen tests keep the text summary.

## Mesh

The Mesh section writes `case/system/blockMeshDict`. Kinds are `box`, `channel`, and `wedge`. `snappyHexMeshDict` uses `first_cell_height`: `cf = 0.058 Re^-0.2`, then `y = y+ * nu / u_tau`. Gmsh is a separate process. `write_gmsh_driver` writes a `.geo` and returns the `gmsh` command. It does not link the Gmsh library.

checkMesh output is parsed for `Mesh OK.`, max non-orthogonality, and max skewness. The default gate is 70 degrees and skewness 4. A real `checkMesh` run needs OpenFOAM and `FOAMSTUDIO_RUNTIME_INTEGRATION=1`.

## Run

The Run section queues `blockMesh` (or snappy), `checkMesh`, and the solver. More than one process adds `decomposePar`, `mpirun`, and `reconstructPar`. Stop calls `taskkill /T /F` on Windows, `kill -- -PID` on Linux and macOS, and the same `kill` inside WSL or over `ssh -o BatchMode=yes`.

`foamstudio --matrix` queues `./Allrun`, which is the step `tests/runtests.sh` already uses. This repository does not replace that script. A full 225-solver matrix was not run from the GUI on this machine.

## Results and reports

Results writes `case.foam`, a `.pvsm` state, and `pvpython_export.py`. ParaView is started as its own program. Slice, clip, iso-lines, and streamlines are plain functions in `foamstudio.core.post.filters`. They do not embed ParaView.

Reports writes HTML. PDF is a Qt print of that HTML (`QPdfWriter`). The problems list is how a missing solver log is reported.

Validation references live in `samples/*/reference.json`.

## Remote

An SSH runtime record needs `host`, `user`, and `bashrc`. FoamStudio calls the `ssh` and `scp` programs. It does not depend on paramiko or asyncssh. A container test needs `FOAMSTUDIO_SSH_INTEGRATION=1`.

## Crash reports

View → Send crash reports stores the choice. The crash file is always written locally. An upload happens only when that choice is on, `FOAMSTUDIO_CRASH_URL` is set, and `FOAMSTUDIO_CRASH_UPLOAD=1`. Updates stay off until an Atom feed URL is configured.
