# FoamStudio: Desktop GUI for OpenFOAM: Master Prompt + Build Plan

> Working name **FoamStudio** (rename freely). Hand this whole file to Claude Code.
> Section 0 is the master prompt; sections 1-12 are the plan it must follow.

---

## 0. MASTER PROMPT (give this to Claude Code)

You are building **FoamStudio**, a cross-platform desktop GUI for OpenFOAM that covers the whole workflow
(import, mesh, set up, run, monitor, post-process, report) and is distributed worldwide as signed installers
for Windows, macOS and Linux.

Read `plan.md` fully before writing code. Follow its architecture, phase order, and acceptance criteria exactly.
Work phase by phase. Do not start phase N+1 until phase N passes its acceptance tests in CI.

Hard rules:
1. **Reuse, don't rewrite.** The existing case generator `openfoam_case_generator.html` (single-file, tested on
   225 cases across ESI v2406/v2412 and Foundation 12/13/14, golden-snapshot tested via `tests/check.js`) is the
   **only** source of truth for writing OpenFOAM dictionaries. Embed and drive it (section 4.3). Never duplicate its logic in Python.
   Changes to dictionary output go into that HTML file, followed by `node tests/check.js --update`, a review of the golden diff,
   a bump of `GEN_VERSION`, and a CHANGELOG line.
2. **Use the open-source components in section 3.** Respect their licences (section 9). Never vendor code without its licence file.
3. **OpenFOAM is never linked.** It is always run as an external process (native, WSL2, Docker, or SSH). The GUI must work with
   ESI (v2006+) and Foundation (9-14) and detect which one is installed.
4. **Every feature ships with tests.** Use pytest and pytest-qt for the GUI, plus the existing `tests/` harness for solver runs.
   CI must be green on Windows, macOS and Linux before a phase is closed.
5. **Never block the UI thread.** Every OpenFOAM call, file read and render is async (QThread/QProcess/asyncio).
6. **No silent failures.** Every subprocess error is surfaced with the exact command, log tail and a suggested fix.
7. **Traceability.** Each case folder contains `case.json` (generator spec) and `foamstudio.json`
   (app version, OpenFOAM version and runtime, command history with timestamps, git-style hashes of inputs).
8. **Ask before** adding a dependency that is not in section 3, changing the licence, or touching anything outside the repo.
9. Keep a running `docs/DECISIONS.md` (ADR style) and update `CHANGELOG.md` every phase.
10. **Output style:** code first, minimal prose, and conventional commits.

Start with Phase 0 (section 7). At the end of each phase, report: what was built, the test results, known gaps, and the next phase plan.

---

## 1. Goal and scope

| In scope (v1.0) | Out of scope (later) |
|---|---|
| Import CAD/mesh (STL, OBJ, STEP via Gmsh, Fluent .msh, Gmsh .msh, existing OpenFOAM case) | Built-in CAD modelling |
| 3D viewer: geometry, mesh, patches, cell zones, quality heat-maps | Overset hole-cutting editor |
| Meshing: blockMesh, snappyHexMesh (incl. layers), Gmsh, checkMesh with quality gates | cfMesh / foamyHexMesh UI |
| Case setup: all 25 solvers of the existing generator, BCs, numerics, rotation, CHT, reacting, VoF | Adjoint optimisation UI |
| Run: local / WSL2 / Docker / SSH+SLURM, parallel, live residuals and monitors, stop/resume | Cloud marketplace |
| Post: embedded viewer (slices, contours, glyphs, streamlines, plots); "Open in ParaView"; batch pvpython reports | Custom VR rendering |
| Reports: HTML/PDF with setup, mesh stats, convergence, integral quantities, y+ | |
| Distribution: signed installers, auto-update, docs site, i18n-ready | |

Target users: students through to industry engineers. The UI is simple by default, with expert mode exposing every dictionary.

## 2. Existing assets (in this repo)

- `openfoam_case_generator.html`: dictionary generator (25 solvers, version-aware, provenance, `case.json`, `applySpec()`/`validateSpec()`).
- `tests/headless.js`, `gen.js`, `check.js`: Node headless generation, golden snapshots and invariants (byte-identical to the browser).
- `tests/mkmesh.sh`, `runtests.sh`, `verify_extra.sh`: real-solver regression (225/225 PASS).
- `.github/workflows/ci.yml`: CI skeleton (not yet run).

## 3. Open-source building blocks (researched; verify the version and licence again at Phase 0)

| Need | Component | Licence | Notes / source |
|---|---|---|---|
| GUI toolkit | **PySide6** (Qt 6) | LGPL-3 | Prefer over PyQt6 (GPL/commercial). Avoid GPL-only Qt add-ons (QtCharts, QtDataVisualization) ([pythonguis](https://www.pythonguis.com/faq/licensing-differences-between-pyqt6-and-pyside6/)) |
| Embedding the generator | **QtWebEngine** (`QWebEngineView` + `QWebChannel`) | LGPL-3 | Loads the existing HTML; JS↔Python bridge |
| 3D view in Qt | **PyVista + pyvistaqt** (VTK) | MIT / BSD-3 | `pv.POpenFOAMReader` for cases, time steps, patches ([PyVista docs](https://docs.pyvista.org/examples/99-advanced/openfoam)) |
| Heavy post-processing | **ParaView** (external app + `pvpython` batch) | BSD-3 | Launch with `.foam` + generated state; never embed ([paraview.org/license](https://paraview.org/license)) |
| Optional web/remote post | **trame** (Kitware) | Apache-2.0 | For remote/HPC rendering in phase 8 ([kitware.com/trame](https://kitware.com/trame)) |
| Case file I/O | **foamlib** | GPL-3 | Parse/write dictionaries and fields, run cases, async ([JOSS 2025](https://joss.theoj.org/papers/10.21105/joss.07633)) |
| Legacy utilities | PyFoam (optional) | GPL-2+ | Only if foamlib lacks a feature |
| Plots (residuals, monitors) | **pyqtgraph** | MIT | Fast live plots without QtCharts |
| Meshing (unstructured) | **Gmsh** (run as subprocess or `.geo` files) | GPL-2+ w/ exception | Do not link it into closed-source code ([gmsh.info](https://www.gmsh.info), [licence notes](https://onelab.info/pipermail/gmsh/2019/013344.html)) |
| Geometry I/O | trimesh / meshio | MIT | STL/OBJ/PLY repair; meshio for format conversion |
| Remote runs | paramiko / asyncssh | LGPL-2.1 / EPL-2 | SSH + SLURM/PBS |
| Packaging | PyInstaller (or Briefcase) | GPL w/ bootloader exception / BSD | Per-OS installers (section 10) |
| macOS OpenFOAM | openfoam-app (gerlero) | GPL-3 | Native macOS OpenFOAM bundle (verify that it is current) |
| Windows OpenFOAM | WSL2 + Ubuntu packages (recommended), Docker, blueCFD-Core | — | WSL2 is the best-supported path ([openfoam.org/download/windows](https://openfoam.org/download/windows/), [OpenFOAMWiki](https://openfoamwiki.net/index.php/Windows)) |

Prior art to study (do not copy code without a compatible licence):
- **FreeCAD CfdOF** (LGPL): workflow and runtime detection on Windows ([github](https://github.com/mmcker/CfdOF)).
- **FoamPilot** (MIT, 2026, Electron+FastAPI+Docker): wizard UX ([CFD Online](https://www.cfd-online.com/Forums/openfoam/262356-foampilot-open-source-desktop-gui-openfoam-electron-fastapi-docker-seeki.html)).
- **OpenFOAM GUI** (Qt case editor) ([docs](https://openfoamgui.readthedocs.io)).
- **SplashFOAM** ([announcement](https://cfddose.substack.com/p/splashfoam-goes-open-source)).
- HELYX-OS and SimFlow are reference UX only (commercial / not open).

## 4. Architecture

```
foamstudio/
  app/                 # Qt application shell (PySide6)
    main.py            # entry, single-instance, crash handler, settings
    mainwindow.py      # dock layout: Project tree | 3D view | Properties | Console/Plots
    theme/             # dark terminal-style theme + light theme (QSS), icons (SVG)
  core/                # no Qt imports here; pure Python, fully unit-tested
    project.py         # Project = folder with case/, geometry/, foamstudio.json
    spec.py            # case.json schema (mirror of the generator's SPEC_SCHEMA), migration
    provenance.py      # foamstudio.json: versions, command log, input hashes
    runtime/           # OpenFOAM runtimes behind one interface
      base.py          # Runtime.detect(), .run(cmd, case, env) -> async process, .version()
      native.py        # Linux/macOS bashrc sourcing (ESI /usr/lib/openfoam*, Foundation /opt/openfoam*)
      wsl.py           # Windows: list distros, path translation C:\ <-> /mnt/c, run via wsl.exe
      docker.py        # opencfd/openfoam images; volume mounts
      ssh.py           # remote host + SLURM/PBS submit/poll/fetch
    jobs.py            # job queue, cancel, resume, parallel (decomposePar/runParallel/reconstructPar)
    logparse.py        # residuals, Courant, continuity, function-object outputs (ESI + Foundation formats)
    mesh/              # blockMesh builder, snappyHexMeshDict builder, Gmsh driver, checkMesh parser + gates
    post/              # pvpython script generation, report builder, y+/forces/torque extraction
  generator/           # bridge to openfoam_case_generator.html
    bridge.py          # QWebChannel object; Python<->JS: applySpec, buildCaseFiles, validateSpec
    headless.py        # fallback: call tests/headless.js via Node for CLI/batch (no Qt)
  ui/                  # widgets
    project_tree.py, viewer3d.py (pyvistaqt), patch_panel.py, mesh_panel.py,
    setup_panel.py (hosts QWebEngineView), run_panel.py, residual_plot.py (pyqtgraph),
    post_panel.py, report_panel.py, runtime_wizard.py, dict_editor.py (QScintilla-free plain editor w/ highlighting)
  cli/                 # `foamstudio run case.json --runtime wsl:Ubuntu-24.04` for batch/CI
tests/                 # pytest + pytest-qt; existing Node/solver harness kept
docs/                  # MkDocs site: user guide, tutorials, DECISIONS.md
packaging/             # PyInstaller specs, Inno Setup/MSIX, dmg, AppImage/Flatpak, signing scripts
```

### 4.1 Data flow
Geometry/mesh import → `Project` → mesh (blockMesh/snappy/Gmsh/convert) → checkMesh gate → patch roles in the viewer →
the generator (WebEngine) produces dictionaries from `case.json` → Runtime runs Allrun steps as tracked jobs → logparse feeds
live plots → post: PyVista in-app, ParaView for depth, pvpython for batch report.

### 4.2 Runtime abstraction (critical for worldwide use)
- `Runtime.detect()` returns every installation found, e.g.
  `[{"kind":"wsl","distro":"Ubuntu-24.04","flavour":"esi","version":"2412","bashrc":"/usr/lib/openfoam/openfoam2412/etc/bashrc"}, ...]`.
- All commands run as `bash -lc 'source <bashrc> && cd <case> && <cmd>'`, via the right transport.
- WSL specifics, learned during this project; encode them as tests:
  - Use `MSYS_NO_PATHCONV`-safe argument passing.
  - Never put `$VAR` in `wsl.exe` command strings: write a temp script into the case and run it.
  - Translate paths both ways.
  - Remove `:Zone.Identifier` files.
  - LF line endings and `chmod +x` for scripts.
  - The WSL `/tmp` is not persistent between calls: use a case-local or `$HOME` work dir.
- A first-run **Runtime Wizard** detects installations and offers guided install:
  - WSL2 + Ubuntu + OpenFOAM (Windows)
  - openfoam-app (macOS)
  - apt repos (Linux)
  - Docker
- Every action shows the exact command it will run.

### 4.3 Generator integration (reuse the tested HTML)
- `setup_panel` hosts the HTML in `QWebEngineView`. A `QWebChannel` object exposes:
  - `py.onSpecChanged(json)` (JS→Py)
  - `js.applySpec(spec)` and `js.buildCaseFiles(name)` (Py→JS, via `runJavaScript`).
- Patch names and roles come from the mesh (the viewer) and are pushed into the generator state. Patch selection in the 3D
  view and patch rows in the generator stay in sync.
- The ZIP download in the HTML is replaced by a "Write case" action that writes `buildCaseFiles()` output into the project folder.
- CLI and batch use `generator/headless.py`, which shells out to `node tests/headless.js`. Node becomes optional: bundle a
  small Node runtime or ship the pre-built JS with QuickJS. Decide in an ADR.

### 4.4 Post-processing strategy
- **In-app (PyVista):**
  - time slider, field and component selection, colour maps and ranges, patch/zone visibility
  - slices, clip, iso-surface, glyphs, streamlines, probes/line plots, integrated forces
  - screenshot/animation export
- **ParaView:**
  - an "Open in ParaView" button that writes `case.foam` and a `.pvsm` state matching the current in-app view
  - detects or downloads ParaView
- **Batch:** `pvpython` scripts generated from templates for images, animations and CSV extracts, used by the report builder.
- **Monitors:** read `postProcessing/*` (forces, surfaceFieldValue, yPlus, residuals) in both ESI and Foundation formats.
  The parsing logic already exists in the generator's `turboPerf.py`; port it into `core/post` with tests.

## 5. UX specification

- Layout: left Project tree (Geometry, Mesh, Setup, Run, Results, Reports), centre 3D viewer, right context properties,
  bottom console with tabs (Log, Residuals, Monitors, Problems).
- **Wizard mode** (6 steps: Geometry → Mesh → Physics → Solver → Run → Results) and **Expert mode** (dictionary editor with
  diff against the generated file; manual edits are recorded in provenance).
- Problems panel: aggregates `validateSpec`, BC validator, checkMesh gates, y+ check and solver errors, with click-to-fix links.
- Units everywhere with SI conversion (input mm/in → m), and every number field shows its unit.
- Dark theme by default (matches the generator), light theme optional; keyboard shortcuts; undo/redo for setup and patch edits.
- i18n via Qt Linguist (`.ts` files) from day one; English first.
- Accessibility: keyboard navigable, scalable fonts, colour-blind-safe colour maps (viridis/cividis default).

## 6. Quality bar

- `core/` ≥ 90% line coverage. UI smoke tests with pytest-qt for every panel.
- Solver regression: the existing 225-case matrix runs via the new Runtime layer, nightly in CI on Linux (ESI 2412 + Foundation 12).
- Golden tests for the generator (`node tests/check.js`) run on every PR.
- Performance targets:
  - open a 5M-cell case in under 10 s (lazy patch loading, decimated preview)
  - UI never blocks for more than 100 ms
  - residual plot handles 1e6 points
- Static checks: ruff, mypy (strict in `core/`), pre-commit hooks.

## 7. Phases with acceptance criteria

| Phase | Deliverable | Acceptance (must pass in CI) |
|---|---|---|
| **0. Foundations** | Repo layout, `pyproject.toml`, ruff/mypy/pytest, CI matrix (win/mac/linux), app shell with docks, settings, logging, crash handler, licence audit script | App launches on all 3 OS in CI (offscreen); `pip-licenses` report shows no GPL-incompatible deps for the chosen app licence |
| **1. Runtime layer** | native/WSL/Docker detection, `Runtime.run` async, Runtime Wizard | Unit tests with fake runtimes; on a Linux runner, detection finds an installed OpenFOAM and `simpleFoam -help` runs; WSL path tests run on the Windows runner (mocked wsl.exe) |
| **2. Project + generator bridge** | Project create/open, QWebEngine-hosted generator, `case.json` ↔ Python sync, "Write case" | Write 25 solvers headless and via the bridge; outputs byte-identical to `tests/golden` |
| **3. Import + viewer** | STL/OBJ/STEP(Gmsh)/Fluent msh/Gmsh msh/OpenFOAM case import; PyVista viewer with patch picking, zones, mesh quality colouring | Import tests on sample files (keep test files <1 MB in repo); patch picking selects the same patch in the generator |
| **4. Meshing** | blockMesh builder (box/channel/axisymmetric wedge), snappyHexMesh builder (refinement regions, layers from target y+), Gmsh driver, checkMesh gate UI | Generated meshes for 3 reference geometries pass checkMesh; layer y+ estimate within 20% of yPlus output on a flat plate |
| **5. Run + monitor** | Job queue, Allrun steps as tracked jobs, live residuals/Courant/monitors, stop/resume, parallel | 225-case matrix passes through the GUI job runner (CLI path in CI); cancelling kills the process tree in WSL and native |
| **6. Post-processing** | In-app post (time, fields, slice/clip/iso/streamlines/plots), ParaView launch with state, pvpython batch export | Screenshot tests (image diff tolerance) on cavity/pitzDaily; ParaView state opens without errors |
| **7. Reports + V&V** | HTML/PDF report: setup, mesh stats, convergence, integral values, y+, GCI helper (3-mesh study) | Report generated for the 3 validation cases with numbers matching reference within stated tolerance |
| **8. Remote/HPC** | SSH runtime, SLURM/PBS templates, file sync, optional trame remote view | Integration test against a container running sshd + OpenFOAM |
| **9. Distribution** | Signed installers, auto-update, docs site, sample projects, telemetry off by default (opt-in crash reports) | Fresh-VM install tests (Win 11, macOS latest, Ubuntu 24.04): install → wizard → run cavity → view results in under 15 min |

## 8. Validation library (ships as sample projects)

Start with these four, each with reference data and tolerances in `samples/<name>/reference.json`:
1. Lid-driven cavity, Re=100 (Ghia et al.)
2. Backward-facing step (Driver & Seegmiller): reattachment length
3. NACA0012 at α=0-10° (Ladson): Cl and Cd
4. Convergent-divergent nozzle (1-D isentropic): Mach and pressure along the axis

Later: mixer vessel torque, damBreak (Martin-Moyce), heated cavity (Nu), plate with hole (Kirsch).

## 9. Licensing (decide in Phase 0, record in an ADR)

- **Recommended: release FoamStudio under GPL-3.0.** foamlib (GPL-3) and Gmsh (GPL-2+) are GPL, and so is the OpenFOAM
  ecosystem. GPL-3 keeps every dependency compatible and allows worldwide free distribution and paid support.
- **If closed source is ever needed:**
  - Drop foamlib for an in-house parser.
  - Call Gmsh only as a separate process.
  - Keep PySide6 dynamically linked (LGPL) and avoid GPL-only Qt modules.
  - Get legal review.
- **OpenFOAM is GPL-3 and is not bundled by default.** If installers bundle it (e.g. a WSL rootfs or a Docker image), ship its
  source offer and licence alongside.
- ParaView, VTK, PyVista, pyqtgraph and trame are permissive (BSD/MIT/Apache).
- Ship `THIRD_PARTY_LICENSES.txt`, generated by the licence audit in CI.

## 10. Packaging and distribution

- **Build:** PyInstaller one-folder builds per OS (QtWebEngine needs its resources; test this early, Phase 0).
- **Windows:**
  - Inno Setup or MSIX installer, Authenticode signing.
  - The Runtime Wizard offers `wsl --install -d Ubuntu-24.04` plus OpenFOAM apt install, run in a visible terminal.
- **macOS:** universal2 build (or separate arm64/x86_64), notarised dmg; recommends openfoam-app or Docker.
- **Linux:** AppImage plus Flatpak (Flathub). OpenFOAM comes from distro repos or Docker.
- **Auto-update:** GitHub Releases feed, verified by signature; staged rollout.
- **Docs:** MkDocs Material site with getting started, tutorials per solver, FAQ (WSL, firewall, antivirus), and the API for the CLI.
- **Community:** GitHub Discussions, issue templates (bug report auto-attaches `foamstudio.json` and log tails), CONTRIBUTING.md, Code of Conduct.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| OpenFOAM version drift (ESI vs Foundation keep changing formats) | All format knowledge stays in the generator; the golden plus real-solver matrix in CI on new releases; the version support table is shown in the UI |
| Windows/WSL fragility (paths, quoting, memory) | Runtime tests, temp-script execution (no inline `$VAR`), WSL memory hint in the wizard, Docker fallback |
| QtWebEngine bundle size/startup | Lazy-load the setup panel; consider porting the generator to Python only if profiling demands it (ADR) |
| Large meshes in viewer | Decimated preview, lazy patch arrays, background loading, LOD |
| Licence mistakes | Automated licence audit in CI; GPL-3 default |
| Scope creep | Phase gates; anything outside the section 1 table goes to the backlog |

## 12. Definition of done (v1.0)

- Every phase acceptance criterion passes in CI on Windows, macOS and Linux.
- The 225-case solver matrix and the 4 validation cases pass through the GUI's own runtime layer.
- Signed installers are on GitHub Releases; the docs site is live; samples are included.
- `THIRD_PARTY_LICENSES.txt` is complete; the licence ADR is recorded.
- A new user on a fresh machine completes install → cavity run → results in under 15 minutes (timed test, recorded).
