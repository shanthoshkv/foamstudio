# FoamStudio handoff

Date: 2026-10-27 for the local checks below. Git publish: 2026-10-28. Author of the app: Shanthosh K V. Working name: FoamStudio.
Workspace: `C:\Users\kvsha\Documents\Learning\openfoam scripting website`.
This folder is a git repository on branch `master`. Remote: `https://github.com/shanthoshkv/foamstudio`. The first push publishes this tree. Do not claim a GitHub Actions result until `gh run list --repo shanthoshkv/foamstudio` shows a completed run. Local Playwright captures in `.playwright-mcp/` are gitignored.

`plan.md` is the master prompt. Phases 0–9 are implemented in the working tree. The version is **0.9.0**, not 1.0. `GEN_VERSION` in `openfoam_case_generator.html` is still **2.2.0**. That HTML file was not edited.

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

Node on this machine is v24.18.0. The existing generator gate is `node tests/check.js`. It was **not** re-run in the phase 3–9 session because `openfoam_case_generator.html` was not edited. Re-run it before touching the generator. Do not run `node tests/check.js --update` unless generator output actually changes.

`tests/conftest.py` forces `QT_QPA_PLATFORM=offscreen`, `FOAMSTUDIO_HEADLESS=1`, and a temp `FOAMSTUDIO_STATE_DIR`. Do not remove that. WebEngine tests pop offscreen and need `FOAMSTUDIO_WEBENGINE=1` plus a real display or xvfb.

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

The 3 skips are the pre-existing gates (WebEngine byte-identity, PyInstaller one-folder build, real OpenFOAM `simpleFoam -help`). The Windows process-tree kill test **did run** and passed (`taskkill /PID <parent> /T /F` in `tests/test_mesh_jobs.py`). It is skipped only when `sys.platform != "win32"`.

Editable install was refreshed. Fallback `foamstudio/__init__.py` is also `"0.9.0"`. If a future edit changes `pyproject.toml` dependencies, run `pip install -e ".[dev]"` again before tests that import new packages, then regenerate `THIRD_PARTY_LICENSES.txt`. Do not hand-edit that file.

## What did not run, and must not be claimed

- GitHub Actions. `.github/workflows/ci.yml` is the workflow named `ci`. The first run is the 2026-10-28 publish push. A comment on the `foamstudio` job says `--matrix` queues `./Allrun` and that this job does not install OpenFOAM. Record pass or fail only from that run.
- The 225-case solver matrix (`tests/runtests.sh`, `node tests/gen.js`). The CLI path is wired (`foamstudio --matrix` queues `./Allrun` via `JobQueue.add_matrix`). No solver case was run.
- Real `checkMesh` / `yPlus` on a mesh. Dict builders and log parsers are unit-tested. Gate a real run behind `FOAMSTUDIO_RUNTIME_INTEGRATION=1`. Do not install OpenFOAM on the 3-OS foamstudio CI job.
- ParaView or `pvpython` opening a state. `state_opens` only parses the XML we write. Screenshot tests use the tiny PNG writer in `foamstudio/core/post/image.py` (mean absolute difference). They are not cavity/pitzDaily renders.
- SSH against sshd. `FOAMSTUDIO_SSH_INTEGRATION=1` is the intended gate. No such test body was added. Argv tests exist.
- PyInstaller (`FOAMSTUDIO_PYINSTALLER=1`), Inno Setup, MSIX, dmg, AppImage, Flatpak, Authenticode. Scripts exist and refuse to pretend. `packaging/signing/sign.ps1` exits 2 without `FOAMSTUDIO_SIGN_PFX`. `packaging/FRESH_VM.md` says the 15-minute install test was **not** executed.
- `node tests/check.js` in the phase 3–9 session.
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
| 6 Post | Field parse, turboForces, ParaView file writer, filters, PNG diff. foamlib may tag a field as source `foamlib` but values come from the ASCII parser. ADR-0009. |
| 7 Reports + V&V | HTML, Qt PDF (`QPdfWriter`, tested offscreen), GCI, nozzle, four `samples/*/reference.json`. Reports compare a perturbed series to the reference. They are not solver results. |
| 8 SSH | OpenSSH client, SLURM/PBS text, scp argv, optional trame **script** (trame is not a dependency). ADR-0007. |
| 9 Distribution | Scripts, MkDocs, CONTRIBUTING, CODE_OF_CONDUCT, issue templates, crash upload off by default, update-feed parser. ADR-0010, ADR-0011. |

ADRs 0001–0011 are in `docs/DECISIONS.md`. Changelog top section is 0.9.0.

## Hard rules (do not regress)

- `openfoam_case_generator.html` is the only solver-dictionary writer. Mesh dictionaries (`blockMeshDict`, `snappyHexMeshDict`) are allowed in `foamstudio/core/mesh/`. Do not use foamlib to write the 25 solver dictionaries.
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
- The remote is `https://github.com/shanthoshkv/foamstudio` on branch `master`. Commit and push only when the user asks.

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
samples/cavity|backward-facing-step|naca0012|nozzle/reference.json
docs/                           MkDocs pages + DECISIONS.md
packaging/                      spec + unsigned installer scripts + FRESH_VM.md
```

CLI order in `main()`: `--detect-runtimes` first; `--project` without an action exits 2; an action without `--project` exits 2; then write-case, import, block-mesh, report, run. Batch-only commands return 0 and do not open the GUI. `--run-case` / `--command` / `--matrix` require `--runtime` JSON or exit 2. `--report` writes HTML even when `case/log.solver` is missing, prints the problem on stderr, and returns 0.

GUI `write_report` and CLI `_report_cli` both call `inputs_for_case`. A missing `case/log.solver` still writes HTML and records "No solver log was found". When the log exists, the final initial residual is recorded. `log.checkMesh`, `log.yPlus` / `log.yPlusCheck`, a `postProcessing` yPlus file, `postProcessing/**/forces*`, and `application` in `system/controlDict` are read when those files exist. GCI stays empty because it needs three meshes. Expert mode says the dictionary editor is under Tools. The highlighter (`Tools → Dictionary editor...`, `foamstudio/ui/dict_editor.py`) is not a second solver-dictionary writer.

## Numbers the tests pin

- Flat plate: `U=1`, `nu=1e-5`, `L=1`, `y+=30` → `first_cell_height` ≈ `0.005570860145311557`. `yplus_matches(30, 31.5)` passes; `40` fails at tolerance 0.2. Do not paste that formula into a fake measured-yPlus fixture.
- GCI: `gci_fine(1.0, 1.1, 1.3, 2)` == `0.125`. Ratio `<= 1` raises `ReportFailure`.
- Nozzle, gamma 1.4: `pressure_ratio(1)` ≈ `0.5282817877171742`. Supersonic `mach_from_area(2)` ≈ `2.1971981216521863`.
- Ghia Re=100 vertical centreline is in `samples/cavity/reference.json`, absolute tolerance 0.05.
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
- Issue template discussion URL is `https://github.com/shanthoshkv/foamstudio/discussions`. Enable Discussions on the repo if that page 404s.
- Inno `AppId` is `{8F3E2A10-6C4B-4A7E-9D11-0F0A0570D109}`. The script was not compiled.
- Later validation samples from `plan.md` (mixer, damBreak, heated cavity, plate with hole) are out of scope.

## Dependencies already in the venv

Declared in `pyproject.toml`: PySide6 Essentials, Addons, WebEngine 6.12; numpy 2.5.4; trimesh 5.2.0; meshio 5.3.5; pyvista 0.49.1; pyvistaqt 0.13.1; pyqtgraph 0.14.0; foamlib 1.9.0; vtk 9.7.1. Dev: pytest, pytest-qt, ruff, mypy, pip-licenses, pre-commit, mkdocs 1.6.1, mkdocs-material 9.8.0. Do not reinstall those wheels unless versions change.

mypy `ignore_missing_imports` covers `meshio` and `foamlib`. pyvista stays out of the core import path.

## Sensible next work

1. Watch the GitHub Actions run on `shanthoshkv/foamstudio`. Fix a red job and push again. A queued run is not a pass.
2. One ESI v2412 `simpleFoam` channel case ran on WSL `Ubuntu-24.04` through `foamstudio --matrix` on 2026-10-28. `log.checkMesh` says `Mesh OK.` and `log.simpleFoam` ends with `End`. The 225-case `tests/runtests.sh` matrix was not run on this machine. `tests/mkmesh.sh` did build the harness meshes into `~/oftest/mesh`. Do not replace `runtests.sh`.
3. With `FOAMSTUDIO_VIEWER=1` and `QT_QPA_PLATFORM=offscreen`, a one-triangle surface builds a `QtInteractor` after points are passed as `(n, 3)` rows. ParaView was not launched. Set `FOAMSTUDIO_PARAVIEW` only when ParaView is installed.
4. Done locally, not pushed while the first Actions run is still going: the GUI report reads `case/log.solver` through `inputs_for_case`.
5. Keep v1.0 blocked until CI is green, installers are signed, and `packaging/FRESH_VM.md` has real clock times.
