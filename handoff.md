# FoamStudio handoff

Date: local checks 2026-10-27. Git publish 2026-10-28. Cavity comparison 2026-10-30.
Author of the app: Shanthosh K V. Working name: FoamStudio.
Workspace: `C:\Users\kvsha\Documents\Learning\openfoam scripting website`.
Branch `master`. Remote: `https://github.com/shanthoshkv/foamstudio`.
HEAD is `1bb4302` (`docs: record the green Actions run`). The working tree is dirty and those edits are not committed:

- `CHANGELOG.md` — cavity bullet under 0.9.0
- `samples/README.md` — cavity run recorded; step, aerofoil, and nozzle still unchecked
- `samples/cavity/case.json` — untracked generator spec used for the cavity
- `handoff.md` — this file

`plan.md` is the master prompt. Phases 0–9 are implemented. The version is **0.9.0**. `GEN_VERSION` in `openfoam_case_generator.html` is **2.2.1** (2026-10-31: waveTransmissive `fieldInf` fix, user approved the bump; goldens regenerated, version-only diff). `foamstudio/core/spec.py` GENERATOR_VERSION matches. Do not claim 1.0.

## How to run anything on this machine

Use the CPython 3.12 venv. Do **not** use `py -3`. On this machine that launcher is free-threaded 3.13t, and PySide6 publishes no wheel for it.

```text
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m ruff check foamstudio tests scripts
.\.venv\Scripts\python -m ruff format --check foamstudio tests scripts
.\.venv\Scripts\python -m mypy
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m foamstudio --self-test
.\.venv\Scripts\python scripts/license_audit.py --check --write THIRD_PARTY_LICENSES.txt
.\.venv\Scripts\python -m mkdocs build --strict
```

Node on this machine is v24.18.0. The existing generator gate is `node tests/check.js`. It was run on this machine before the publish push, and the quality job passed. Re-run it before touching the generator. Do not run `node tests/check.js --update` unless generator output actually changes.

`tests/conftest.py` forces `QT_QPA_PLATFORM=offscreen`, `FOAMSTUDIO_HEADLESS=1`, and a temp `FOAMSTUDIO_STATE_DIR`. Do not remove that. WebEngine tests pop offscreen and need `FOAMSTUDIO_WEBENGINE=1` plus a real display or xvfb.

PowerShell 5.1 has no `&&`. Chain with `;`. WSL default distro is `Ubuntu-24.04`. OpenFOAM bashrc: `/usr/lib/openfoam/openfoam2412/etc/bashrc`. A reusable runtime record is `%TEMP%\fs-one\runtime.json` (`kind` wsl, `flavour` esi, `version` 2412, that bashrc, `distro` Ubuntu-24.04).

## What passed locally (2026-10-27)

| Check | Result |
| --- | --- |
| ruff check + ruff format --check | clean |
| mypy | 35 files in `foamstudio.core`, no issues |
| pytest | **150 passed, 3 skipped** in about 44 s |
| `python -m foamstudio --self-test` | printed `foamstudio: launched` |
| `scripts/license_audit.py --check` | `Incompatible: 0`. `THIRD_PARTY_LICENSES.txt` was regenerated after the scientific wheels and MkDocs |
| `mkdocs build --strict` | built, then the generated `site/` directory was deleted. `site/` is in `.gitignore` |
| importlib version | `foamstudio.__version__` is `0.9.0` after `pip install -e ".[dev]"` |

The full pytest count was not re-run after the report and viewer edits. Those edits were covered by a targeted pytest before commit `798ecb6`. The 3 skips are the pre-existing gates (WebEngine byte-identity, PyInstaller one-folder build, real OpenFOAM `simpleFoam -help`). The Windows process-tree kill test **did run** and passed (`taskkill /PID <parent> /T /F` in `tests/test_mesh_jobs.py`). It is skipped only when `sys.platform != "win32"`.

Editable install was refreshed. Fallback `foamstudio/__init__.py` is also `"0.9.0"`. If a future edit changes `pyproject.toml` dependencies, run `pip install -e ".[dev]"` again before tests that import new packages, then regenerate `THIRD_PARTY_LICENSES.txt`. Do not hand-edit that file.

## Git and CI

Publish commit `4bc1c54` completed Actions run [40618797616](https://github.com/shanthoshkv/foamstudio/actions/runs/40618797616) with conclusion success in 6m33s. Follow-up `1bb4302` completed run [40620644207](https://github.com/shanthoshkv/foamstudio/actions/runs/40620644207), also success. Both runs: quality, foamstudio (Windows, macOS, Linux), generator (linux webengine), runtime (linux), openfoam (12), openfoam (2412).

Solver artifacts, counted from the downloaded logs: 39 PASS / 0 FAIL for Foundation 12 and 40 PASS / 0 FAIL for ESI 2412. `verify.txt` has no BAD line. That is the current `tests/runtests.sh` set. Do not call it 225 cases. The `foamstudio` job does not install OpenFOAM. `foamstudio --matrix` queues `./Allrun`. Do not start another Actions watcher unless a new commit is pushed.

GitHub Discussions are enabled. The issue template points at `https://github.com/shanthoshkv/foamstudio/discussions`. GitHub Pages was not deployed. `mkdocs build --strict` only proves the site builds.

`checkMesh` and a yPlus report ran inside those CI cases. The 2412 yPlus note says walls avg 60.9. That is not a flat-plate y+ match. The runtime job is `simpleFoam -help` under `FOAMSTUDIO_RUNTIME_INTEGRATION=1`, and that job passed.

## Local solver runs

Channel, 2026-10-28. ESI v2412 `simpleFoam` through `foamstudio --matrix` on WSL `Ubuntu-24.04`. Project `%TEMP%\fs-one`. Mesh copied from `~/oftest/mesh/channel2d` after `tests/mkmesh.sh`. `log.checkMesh` says `Mesh OK.` `log.simpleFoam` ends with `End`. Do not replace `runtests.sh`.

Cavity, 2026-10-30. Laminar lid-driven cavity, Re=100, same WSL runtime. Project `%TEMP%\fs-cavity` (outside git). Spec now in `samples/cavity/case.json`: `simpleFoam`, `turbModel` laminar, `nu` 0.01, lid patch `yMax` type `translatingWallVelocity` with U = (1 0 0), walls `xMin` / `xMax` / `yMin` left to the generator default `noSlip`, `zMin` / `zMax` role `empty`. Control `endTime` 1000, `writeInterval` 1000, residuals `1e-12` so `residualControl` does not stop before the only write.

FoamStudio wrote the dictionaries with `--write-case`. Python wrote `system/blockMeshDict` via `block_mesh_dict("box", length=1, height=1, width=0.1, cells=(64, 64, 1))`. CLI `--block-mesh` cannot set the cell counts. The run command that worked was `bash ./Allrun`. `bash Allrun` fails: `Allrun` does `cd "${0%/*}"`, and without the `./` that path is the script name. `log.checkMesh` says `Mesh OK.` `log.simpleFoam` ends with `End` at time 1000. Execution time about 6 s, clock time about 14 s. At time 1000 the U initial residuals were about 4.8e-5. `blockMesh` printed an IOWarning that `convertToMeters` is older than `scale`. The mesh still built. Leave `convertToMeters` in place; older supported OpenFOAM versions use that keyword.

Sampling: ESI v2412 `sets` rejects type `lineUniform`. The dict that worked is `system/sampleDict`, type `sets`, set type `uniform`, axis `y`, from `(0.5 0 0.05)` to `(0.5 1 0.05)`, 201 points, field `U`. Command: `postProcess -func sampleDict -latestTime`. Output: `postProcessing/sampleDict/1000/vertical_U.xy` (columns y, Ux, Uy, Uz). Ux was interpolated onto the Ghia y stations and passed to `compare_series`. All 17 stations passed tolerance 0.05. Largest absolute error 0.0121 at y = 0.7344. This clock time is the solver only. It is not the fresh-VM install test.

`onSolverChange()` in the HTML generator refreshes widgets and the apply path restores `control`. It did not wipe `nu` or the patches on this spec. Confirm `0/U`, `constant/transportProperties`, and `constant/turbulenceProperties` after any new spec before solving. Do not copy the stock icoFoam cavity tutorial. That tutorial is a different Reynolds number.

## Do not claim these

- Version 1.0. (The generator was edited once on 2026-10-31 for the waveTransmissive fix, as 2.2.1.)
- Backward-facing step, NACA 0012, and nozzle solver comparisons. Their `reference.json` files exist. No OpenFOAM run has been compared for them.
- ParaView or `pvpython` opening a state. `state_opens` only parses the XML FoamStudio writes. WSL has `/usr/bin/paraview` and `/usr/bin/pvpython`. Neither has been launched from FoamStudio. Screenshot tests use the tiny PNG writer in `foamstudio/core/post/image.py`.
- SSH against sshd. `FOAMSTUDIO_SSH_INTEGRATION=1` is the intended gate. No such test body was added. Argv tests exist.
- PyInstaller (`FOAMSTUDIO_PYINSTALLER=1`), Inno Setup, MSIX, dmg, AppImage, Flatpak, Authenticode. Scripts exist and refuse to pretend. `packaging/signing/sign.ps1` exits 2 without `FOAMSTUDIO_SIGN_PFX`. `packaging/FRESH_VM.md` says the 15-minute install test was not executed. Do not invent clock times.
- A live docs site. The MkDocs build was local. GitHub Pages was not deployed.
- Interactive PyVista slice/clip/iso/streamline widgets. The math is in `foamstudio/core/post/filters.py` and is tested. The 3D widget is a summary label unless `FOAMSTUDIO_VIEWER=1`.

## Status by phase

| Phase | State |
| --- | --- |
| 0 Foundations | Done earlier. GPL-3.0-only, Qt shell, licence audit, CI workflow file. ADR-0001, ADR-0002. |
| 1 Runtime | Done earlier. Native, WSL, Docker as external processes. WSL never puts `$VAR` in `wsl.exe` argv. Docker is the `docker` CLI. ADR-0004. |
| 2 Project + generator | Done earlier. Node `tests/headless.js` is the headless writer. WebEngine is the GUI host. Python does not write the 25 solver dictionaries. ADR-0005, ADR-0006. |
| 3 Import + viewer | Coded and unit-tested. Startup centre widget stays the QLabel `viewer` ("No geometry loaded.") until `MainWindow.import_geometry`. Tree clicks swap the **properties dock**, not the centre. ADR-0008. |
| 4 Meshing | Coded and unit-tested. `blockMeshDict` box/channel/wedge, `snappyHexMeshDict`, Gmsh subprocess driver, `checkMesh` parser. |
| 5 Run + monitor | Coded and unit-tested with a fake probe (`live=False`). CLI `--run-case` uses `live=True`. GUI uses a second `QThread`. |
| 6 Post | Field parse, turboForces, ParaView file writer, filters, PNG diff. foamlib may tag a field as source `foamlib` but values come from the ASCII parser. ADR-0009. A real ParaView process has not opened a state. |
| 7 Reports + V&V | HTML, Qt PDF (`QPdfWriter`, tested offscreen), GCI, nozzle, four `samples/*/reference.json`. Unit tests compare a perturbed series. The 2026-10-30 cavity run is a separate, real solver comparison. The other three samples have no solver comparison. |
| 8 SSH | OpenSSH client, SLURM/PBS text, scp argv, optional trame **script** (trame is not a dependency). ADR-0007. |
| 9 Distribution | Scripts, MkDocs, CONTRIBUTING, CODE_OF_CONDUCT, issue templates, crash upload off by default, update-feed parser. ADR-0010, ADR-0011. Installers were not built or signed. |

ADRs 0001–0011 are in `docs/DECISIONS.md`. Changelog top section is 0.9.0. ADR-0004 still says "SSH stays Phase 8". ADR-0007 is the later decision that SSH uses OpenSSH. Do not rewrite ADR-0001–0006.

## Hard rules (do not regress)

- `openfoam_case_generator.html` is the only solver-dictionary writer. Mesh dictionaries (`blockMeshDict`, `snappyHexMeshDict`) and a post-processing `sampleDict` are allowed. Do not use foamlib to write the 25 solver dictionaries.
- Do not bump `GEN_VERSION` or rewrite `tests/golden/` unless generator output changes.
- OpenFOAM, Gmsh, and ParaView are external processes. Never link them.
- `foamstudio/core` is Qt-free and mypy-strict (`packages = ["foamstudio.core"]`). `tests/test_licenses.py` rglob-asserts no `PySide`/`PyQt` under `core/`.
- Do not import Qt Charts or Qt Data Visualization. `packaging/foamstudio.spec` excludes them.
- Do not add paramiko, asyncssh (EPL, not on the allow-list), docker-py, trame as a required dep, pyinstaller, or a third-party PDF library.
- Licence audit fails closed. SPDX `AND` means every clause must pass. Allow-list includes `cc0` because NumPy 2.5.4 reports `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`. EPL is not allowed. GPL-2.0-only is rejected. The regex must not treat LGPL-2.1 as GPL-2-only.
- QAction.triggered and QPushButton.clicked emit a bool. Slots must swallow it (`lambda _checked=False:`).
- `HEADLESS` / `--self-test` must not open the runtime wizard or a WebEngine view.
- `Installation.to_dict()` omits `host`/`user` unless `kind=="ssh"`. A WSL dict must not contain `image`. Missing ssh host/user errors contain the word `ssh` (`tests/test_runtime.py` matches that).
- `SettingsModel` is frozen. `crash_reports` defaults False so the 3-arg constructor in `tests/test_settings_model.py` still works. Window copies use `dataclasses.replace`.
- `QSettings.value(..., type=bool)` is not used for `wizard_done`.
- English catalog `foamstudio/app/i18n/foamstudio_en.ts` must keep the sources `Geometry`, `No geometry loaded.`, `New project...`, `Write case`, `Case generator ready.` (`tests/test_app_shell.py`).
- `tests/test_app_shell.py::test_shell_layout` requires `window.centralWidget() is window.viewer`, viewer text `No geometry loaded.`, and the six tree labels Geometry, Mesh, Setup, Run, Results, Reports. Clicking those items must not replace the startup label. Import does.
- Live jobs pass `launch_env()` so `MSYS_NO_PATHCONV=1` is set. Unit tests of `JobQueue` should keep `live=False` so they hit the probe, not a real shell.
- Crash POST happens only when a plan exists **and** `FOAMSTUDIO_CRASH_UPLOAD=1`. Tests must not set that flag. `maybe_upload` does not open a socket.
- `detect()` does not scan SSH unless a record is configured.
- Do not put `$` in `wsl.exe` argv. SSH rejects `$` in host, user, remote path, and bashrc. A `$` inside the remote `bash -lc` script body is acceptable.
- Ask before adding a dependency that is not already in `plan.md` section 3, before changing the licence, and before writing outside this repo.
- Commit and push only when the user asks. The remote is `https://github.com/shanthoshkv/foamstudio` on branch `master`.

## Layout the next session will touch

```text
foamstudio/app/main.py          CLI. No required subcommand. --self-test must stay first-class.
foamstudio/app/mainwindow.py    Docks, import, mesh, run, ParaView, report, dictionary editor.
foamstudio/app/crash.py         Local file always. Upload is gated.
foamstudio/core/geometry/       STL/OBJ/Gmsh/Fluent/STEP/OpenFOAM boundary.
foamstudio/core/mesh/           blockMesh, snappy, Gmsh driver, checkMesh parse.
foamstudio/core/jobs.py         Queue, ./Allrun, kill_argv.
foamstudio/core/logparse.py     Residuals, Courant, monitor tables.
foamstudio/core/post/           fields, turbo, paraview, report, image, filters.
foamstudio/core/runtime/ssh.py  ssh/scp/slurm/pbs/trame script.
foamstudio/core/telemetry.py    maybe_upload.
foamstudio/core/update.py       Atom feed parser. Nothing enables it.
foamstudio/ui/                  Panels. PyVista and pyqtgraph are lazy.
samples/cavity/case.json        Untracked spec for the Re=100 cavity.
samples/cavity|backward-facing-step|naca0012|nozzle/reference.json
docs/                           MkDocs pages + DECISIONS.md
packaging/                      spec + unsigned installer scripts + FRESH_VM.md
```

CLI order in `main()`: `--detect-runtimes` first; `--project` without an action exits 2; an action without `--project` exits 2; then write-case, import, block-mesh, report, run. Batch-only commands return 0 and do not open the GUI. `--run-case` / `--command` / `--matrix` require `--runtime` JSON or exit 2. `--report` writes HTML even when `case/log.solver` is missing, prints the problem on stderr, and returns 0.

GUI `write_report` and CLI `_report_cli` both call `inputs_for_case`. A missing `case/log.solver` still writes HTML and records "No solver log was found". When the log exists, the final initial residual is recorded. `log.checkMesh`, `log.yPlus` / `log.yPlusCheck`, a `postProcessing` yPlus file, `postProcessing/**/forces*`, and `application` in `system/controlDict` are read when those files exist. GCI stays empty because it needs three meshes. Expert mode says the dictionary editor is under Tools. The highlighter (`Tools → Dictionary editor...`, `foamstudio/ui/dict_editor.py`) is not a second solver-dictionary writer.

With `FOAMSTUDIO_VIEWER=1` and `QT_QPA_PLATFORM=offscreen`, a one-triangle surface builds a `QtInteractor` after points are passed as `(n, 3)` rows. That check was local. It is in the pushed viewer fix `798ecb6`.

## Numbers the tests pin

- Flat plate: `U=1`, `nu=1e-5`, `L=1`, `y+=30` → `first_cell_height` ≈ `0.005570860145311557`. `yplus_matches(30, 31.5)` passes; `40` fails at tolerance 0.2. Do not paste that formula into a fake measured-yPlus fixture.
- GCI: `gci_fine(1.0, 1.1, 1.3, 2)` == `0.125`. Ratio `<= 1` raises `ReportFailure`.
- Nozzle, gamma 1.4: `pressure_ratio(1)` ≈ `0.5282817877171742`. Supersonic `mach_from_area(2)` ≈ `2.1971981216521863`.
- Ghia Re=100 vertical centreline is in `samples/cavity/reference.json`, absolute tolerance 0.05. The 2026-10-30 run's largest error was 0.0121.
- Backward-facing step reattachment `6.26 ± 0.5`.
- NACA 0012: Cl(0)=0, Cd(0)=0.008, Cl(10)=1.025 with the tolerances in `samples/naca0012/reference.json`.

## UI verification

This is a Qt desktop app. Browser tools do not apply. Verification is pytest-qt offscreen.

- Constructing `ResidualPlot` and calling `set_samples([])` is safe.
- Calling `set_samples` with data imports pyqtgraph and builds a `PlotWidget`. The panel test monkeypatches `_try_plot` so the default suite does not do that. Do not call the real plotter under offscreen unless you are ready for a native crash.
- `Viewer3D` imports PyVista only when `FOAMSTUDIO_VIEWER=1`. Leave widget construction behind that flag.
- `write_pdf` in `foamstudio/ui/report_panel.py` worked under offscreen in `tests/test_panels_phase.py::test_pdf_report`.

## Known limits (worked as designed, still incomplete)

- Slice/clip/iso/streamline are pure functions on triangles and a cartesian velocity callable. There is no VTK filter widget and no in-viewer plane drag.
- `JobQueue._run_live` stores `pid` and `communicate()`s. Cancel during that wait depends on another caller running `kill_argv`. The Windows test kills a sleep tree. It does not cancel a live OpenFOAM run.
- Fluent import is tested by monkeypatching `meshio.read`, not with a binary `.msh` fixture.
- STEP import is tested with a fake `gmsh` launcher that writes a tiny msh 2.2 file.
- foamlib is installed (1.9.0, GPL-3.0-only, allowed). `read_field` accepts source `ascii` or `foamlib`. It must not mutate the file (foamlib `FoamFile` is a writable mapping).
- The report solver name is the `application` entry in `system/controlDict` when that line exists. Otherwise it stays "recorded in system/controlDict".
- Update rollout parser exists. No UI turns updates on.
- Inno `AppId` is `{8F3E2A10-6C4B-4A7E-9D11-0F0A0570D109}`. The script was not compiled.
- Later validation samples from `plan.md` (mixer, damBreak, heated cavity, plate with hole) are out of scope.
- The WSL runner chmods `.foamstudio/run.sh`, not `Allrun`. Invoke Allrun as `bash ./Allrun` unless the case file is already executable.

## Dependencies already in the venv

Declared in `pyproject.toml`: PySide6 Essentials, Addons, WebEngine 6.12; numpy 2.5.4; trimesh 5.2.0; meshio 5.3.5; pyvista 0.49.1; pyvistaqt 0.13.1; pyqtgraph 0.14.0; foamlib 1.9.0; vtk 9.7.1. Dev: pytest, pytest-qt, ruff, mypy, pip-licenses, pre-commit, mkdocs 1.6.1, mkdocs-material 9.8.0. Do not reinstall those wheels unless versions change.

mypy `ignore_missing_imports` covers `meshio` and `foamlib`. pyvista stays out of the core import path.

## Next work

1. DONE 2026-10-31. pvpython (WSL) opened `%TEMP%\fs-cavity\case\case.foam`: times [1000.0], fields U and p. The hand-written `write_state` XML loaded **zero sources** in `LoadState`, so it is not valid. Fix: `pvpython_script(foam, image, state)` now emits `SaveState`; the GUI no longer calls `write_state` (kept, commented as not loadable). Generated script ran headless (`pvpython --force-offscreen-rendering`, rc 0) and wrote a PNG and a 186 KB `.pvsm`. The 4.5 KB PNG was not visually inspected. WSL paths: `pvpython_script(..., wsl=True)` rewrites `C:/x` to `/mnt/c/x` via `windows_to_wsl`; the GUI sets it when the saved runtime kind is `wsl`. Verified with a real Windows case path in WSL pvpython (rc 0, PNG + `.pvsm` written). The screenshot shows the cavity square but is not coloured by U. Not tested: GUI "Open in ParaView" launch (`launch_argv` still passes a host path), the GUI button itself. Edits to `paraview.py`, `mainwindow.py`, `tests/test_post_report.py` are uncommitted.
2. Backward-facing step RAN 2026-10-31 and FAILED the check: xr/h 5.54 / 5.32 vs 6.26 ± 0.5 (see `samples/README.md`; project `%TEMP%s-step`). Ux column in `raw` sets with `axis x` is column 1 (x, Ux, Uy, Uz); sample z must be inside the 1.27 mm slab. Suspects: thin inlet boundary layer (10h run-up), one mesh, SST. Next: longer run-up and a refined mesh before judging; do not retune to pass. Original item text: Reference `samples/backward-facing-step/reference.json`: reattachment length 6.26, tolerance 0.5. NACA 0012 and the nozzle come after the step.
2c. 2026-10-31 later: step 50h run-up xr/h 5.90 (marginal PASS); nozzle FAIL (+1.7 % / -1.9 % vs 1 %); NACA not run (needs a C-mesh); WSL cancel fixed (Linux pgid); report provenance; PyInstaller bundle works (931 MB); release/docs/SSH workflows added, none run on GitHub; generator waveTransmissive fieldInf fixed, GEN_VERSION bumped to 2.2.1 (user approved). Details: docs/validation.md, samples/README.md, packaging/README.md.
2b. 2026-10-31 Stage B done locally (plan `~/.claude/plans/read-the-files-md-rosy-sutton.md`): pip-audit clean, SBOM 118 components, CodeQL + Dependabot + SECURITY.md, coverage gate 87 (87.79%), 152 passed / 3 skipped. Licence stays GPL-3.0-only (user decision). Not verified on GitHub: CodeQL run, Dependabot, private vulnerability reporting (enable in repo Settings → Security). The 50h step run (`%TEMP%s-step50`) died at ~180 s; rerun at the end, 30-minute cap (user).
3. Keep version 0.9.0. Signed installers and `packaging/FRESH_VM.md` still have no certificate and no fresh machine. Do not invent those results.
4. Commit the cavity notes only when the user asks. Do not push unless asked.
