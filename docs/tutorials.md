# Tutorials

These are the paths the CLI can run without a display. A solver tutorial still needs an OpenFOAM installation.

## Cavity dictionaries

1. Save a `case.json` from the HTML generator (lid-driven cavity, `icoFoam` or `simpleFoam`).
2. `foamstudio --write-case case.json --project cavity`
3. Compare `samples/cavity/reference.json` after you have a sampled centerline. The Ghia tolerance in that file is 0.05.

The generator remains the dictionary writer. Do not hand-edit a second copy of those dictionaries in Python.

## Block mesh

```text
foamstudio --project channel --block-mesh channel
```

This writes `channel/case/system/blockMeshDict`. Open the project and use File → Write case for the solver dictionaries.

## Report after a run

```text
foamstudio --project cavity --report cavity\report.html
```

If `case/log.solver` is missing, the command prints that path and still writes the HTML. The problems section is the failure. It is not hidden.

## 225-case matrix

On a machine with OpenFOAM and a runtime JSON from `--detect-runtimes`:

```text
foamstudio --project cases --runtime runtime.json --matrix --run-case
```

That queues `./Allrun`. The known-good loop is still `bash tests/runtests.sh`. CI runs that script in the `openfoam` job. It does not install OpenFOAM into the three-OS `foamstudio` job.

## ParaView

From the Results section, write the state, then:

```text
paraview case\case.pvsm
```

If `paraview` is not on `PATH`, set `FOAMSTUDIO_PARAVIEW`. FoamStudio does not ship ParaView.
