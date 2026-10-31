# Changelog

## FoamStudio 0.9.0

Phases 3–9 in the working tree. The case generator is unchanged (`GEN_VERSION` 2.2.0). This is not a 1.0 release. GitHub Actions run [40618797616](https://github.com/shanthoshkv/foamstudio/actions/runs/40618797616) on `4bc1c54` passed in 6m33s: quality, foamstudio on Windows, macOS, and Linux, the WebEngine generator, `simpleFoam -help` on ESI v2412, and the solver jobs. Those jobs recorded 39 PASS for Foundation 12 and 40 PASS for ESI 2412, with no FAIL or BAD line. Signed installers, a fresh-VM timing run, ParaView, and sshd were not executed.

- Import STL, OBJ, Gmsh 2.2/4.1, Fluent `.msh`, STEP via the `gmsh` executable, and OpenFOAM `constant/polyMesh`. The centre view stays a label until an import succeeds. PyVista loads only when `FOAMSTUDIO_VIEWER=1`.
- `blockMeshDict` for box, channel, and wedge. `snappyHexMeshDict` first-cell height from a flat-plate y+ estimate. Gmsh stays a subprocess.
- Job queue for Allrun steps and `./Allrun` (`foamstudio --matrix`). Stop kills the process tree. Live runs set `MSYS_NO_PATHCONV=1`.
- Field reader, turboForces numbers, HTML report, GCI, nozzle checks, and `samples/*/reference.json`. PDF uses Qt `QPdfWriter`. ParaView is an external `.foam` / `.pvsm` launch.
- SSH uses the system `ssh`/`scp` client. Crash upload stays off unless `FOAMSTUDIO_CRASH_UPLOAD=1`. Update feed parsing is inert until configured.
- Packaging scripts, MkDocs pages, contributing notes, and issue templates. `sign.ps1` refuses to sign without a certificate.
- The window report and `foamstudio --report` read the same case files: `log.solver`, `log.checkMesh`, yPlus logs, `postProcessing/**/forces*`, and `application` in `system/controlDict` when that line is present. Expert mode points at Tools → Dictionary editor.
- PyVista receives triangle points as `(n, 3)` rows. A flat coordinate list was rejected before a mesh could be drawn.
- Supply chain: `pip-audit` CVE scan and CycloneDX SBOM in CI, CodeQL workflow, Dependabot, `SECURITY.md`, coverage gate on `foamstudio/core` (87%, measured 87.79%). Dev deps added: pytest-cov, pip-audit, cyclonedx-bom.
- ParaView: `pvpython_script` writes the state through `SaveState` (the hand-written `.pvsm` loaded zero sources) and maps Windows paths to `/mnt/<drive>` for WSL.
- Generator: `waveTransmissive` wrote `fieldInf uniform <v>`; OpenFOAM v2412 needs a bare value and aborted. No golden file uses that BC. `GEN_VERSION` bumped 2.2.0 -> 2.2.1; golden snapshots regenerated, and they differ only in the version string and spec hash.
- WSL cancel kills the Linux process group; reports read `log.<application>` and include provenance; PyInstaller bundle starts; release, docs and SSH-integration workflows added (not run on GitHub yet).
- Local step rerun with a 50h run-up: xr/h 5.90 (near-wall line) vs 6.26 ± 0.5, marginal pass; 5.64 at 1 mm.
- Local nozzle run: choked, exit M +1.7 %, throat p/p0 −1.9 % vs 1-D theory (1 % tolerance): does not pass. NACA 0012 not run.
- Local ESI v2412 cavity: laminar `simpleFoam`, 64×64×1, 1000 iterations. The sampled vertical centerline matched Ghia Re=100 with a largest absolute error of 0.0121, inside the 0.05 tolerance in `samples/cavity/reference.json`. The spec is `samples/cavity/case.json`. The aerofoil and nozzle were not run in that check.
- Local ESI v2412 backward-facing step, kOmegaSST: reattachment xr/h 5.54 and 5.32 versus 6.26 ± 0.5. Does not pass. Spec in `samples/backward-facing-step/`.

## FoamStudio 0.3.0

Phase 2 project and generator bridge. The case generator is unchanged (`GEN_VERSION` 2.2.0).

- A project folder holds `case/`, `geometry/`, and `foamstudio.json` (version, command log, git blob hashes).
- Write case runs `openfoam_case_generator.html` through Node (`tests/headless.js`) or through Qt WebEngine. Python does not write dictionaries.
- `foamstudio --write-case case.json --project DIR` writes a case without opening the window.
- PySide6 Addons supplies Qt WebChannel. PySide6 6.12 supplies Qt WebEngine in `PySide6_WebEngine`. Qt Charts and Qt Data Visualization are not imported.

## FoamStudio 0.2.0

Phase 1 runtime layer. The case generator is unchanged (`GEN_VERSION` 2.2.0).

- Detect native, WSL, and Docker OpenFOAM installations and run a command asynchronously through one interface.
- WSL runs a case-local LF script. Arguments passed to `wsl.exe` do not contain `$`.
- Runtime Wizard shows the exact command, offers install commands, and saves the chosen runtime.
- Linux CI job installs ESI OpenFOAM 2412 and runs `simpleFoam -help` when `FOAMSTUDIO_RUNTIME_INTEGRATION=1`.

## FoamStudio 0.1.0

Phase 0 foundations. The case generator is unchanged (`GEN_VERSION` 2.2.0).

- GPL-3.0-only application licence (ADR-0001). PySide6 Essentials only (ADR-0002).
- Qt shell: project tree, viewer placeholder, properties, console, dark/light theme, settings, logging, crash report, single-instance guard.
- `scripts/license_audit.py` fails closed on packages that cannot be combined with GPL-3.0-only.
- CI launches the shell offscreen on Windows, macOS, and Linux.

## Case generator

Generator version is `GEN_VERSION` in `openfoam_case_generator.html`; it is stamped into every generated
dictionary and into `case.json`. Bump it whenever generated output changes, and update
`tests/golden` in the same change (`node tests/check.js --update`, then review the diff).

## 2.2.0
- `case.json` gains `schema: 1`; specs are validated on load (solver, version, patch names/roles, numbers, control).
- `applySpec()` / `validateSpec()` split out of the UI so they are testable headless.
- Test tooling: headless generator (`tests/headless.js`, `gen.js`), golden snapshots + invariants
  (`tests/check.js`), CI workflow (`.github/workflows/ci.yml`).

## 2.1.0
- Provenance line in every dictionary; `case.json` in every ZIP; "Load case.json" button.
- Allrun: checkMesh quality gate (stop on failed checks, auto non-orthogonal correction), y+ report.
- ESI steady runs stop on inlet-pressure convergence (`runTimeControl`).
- Fixes: potentialFoam `Phi` solver, per-region `decomposeParDict` for ESI CHT, Foundation torque in `turboPerf.py`.

## 2.0.0
- Solver registry (25 solvers), version-aware generation for ESI v2006+ and Foundation 5–14.
- Rotation (MRF/AMI/SRF/overset/rotor disk), CHT multi-region, reacting, XiFoam, VoF/cavitation, solid.
- 225-case regression on ESI v2406/v2412 and Foundation 12/13/14.
