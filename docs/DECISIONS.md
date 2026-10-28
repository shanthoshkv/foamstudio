# Decisions

## ADR-0001: Release FoamStudio under GPL-3.0-only

Date: 2026-10-27
Status: accepted

### Context

The OpenFOAM ecosystem is GPL-3.0. foamlib (GPL-3.0) and Gmsh (GPL-2.0 or later) are on the Phase 1–4 dependency list. PySide6 is available under LGPL-3.0, GPL-2.0, or GPL-3.0, with a separate commercial licence. A permissive application licence would not be able to depend on foamlib.

### Decision

FoamStudio is GPL-3.0-only. PySide6 is used under its GPL-3.0 grant. OpenFOAM is not bundled. If an installer later ships OpenFOAM, that installer also ships OpenFOAM's licence and source offer.

### Consequences

GPL-2.0-only code cannot be added. LGPL, MIT, BSD, Apache-2.0, MPL-2.0, and GPL-3.0 dependencies can. `scripts/license_audit.py` fails the build when an installed package does not meet that rule. A closed-source build would mean a new ADR: drop foamlib, keep Gmsh a separate process, and get legal review before leaving GPL-3.0.

## ADR-0002: Phase 0 links PySide6 Essentials only

See ADR-0006 for the Phase 2 Qt WebEngine dependency.

Date: 2026-10-27
Status: accepted

### Context

`pip install PySide6` pulls `PySide6_Addons`, which through 6.11 included Qt WebEngine together with the Qt Charts / Qt Data Visualization modules. PySide6 6.12 moved WebEngine to `PySide6_WebEngine` (ADR-0006). The plan says to avoid those GPL-only Qt add-ons. Qt WebEngine is also the packaging risk called out for a one-folder PyInstaller build, and Phase 0 does not open the case generator.

PySide6_Essentials 6.12 (October 2026) provides Qt Core, Gui, Widgets, Svg, Network, and the other Essentials modules. `pip-licenses` reports `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` for both `PySide6_Essentials` and `shiboken6`. The audit selects the LGPL-3.0-only alternative. The GPL-2.0-only alternative is not used. Wheels exist for regular CPython on Windows, macOS universal2, and manylinux. They do not exist for free-threaded CPython (`cp313t`).

### Decision

Phase 0 depends on `PySide6_Essentials` only. The in-app 3D view (PyVista) and the generator view (Qt WebEngine) are not dependencies yet. `packaging/foamstudio.spec` excludes Qt WebEngine and Qt Charts. The one-folder PyInstaller smoke that has to collect WebEngine resources runs in Phase 2, when the setup panel actually loads `openfoam_case_generator.html`.

### Consequences

The Phase 0 install is smaller and the licence audit does not see the add-on wheels. Phase 2 adds WebEngine explicitly (ADR-0006), re-runs the licence audit, and checks that the install contains Qt WebEngine's process and resource files. Local and CI interpreters must be regular CPython, not a free-threaded build.

## ADR-0003: Node remains the headless generator host until Phase 2

Date: 2026-10-27
Status: superseded by ADR-0005

### Context

`tests/headless.js` already produces dictionary output byte-identical to the browser. The plan asks for an ADR on bundling Node or shipping the generator script on QuickJS before the CLI calls it.

### Decision

Phase 0 does not shell out to the generator. The existing Node harness stays the quality gate. Phase 2 chooses the embedded runtime when `generator/headless.py` is written, and records the choice by updating this ADR.

### Consequences

No second dictionary writer exists. `GEN_VERSION` stays 2.2.0.

## ADR-0004: WSL and Docker are external processes

Date: 2026-10-27
Status: accepted

### Context

Windows needs WSL, and every platform needs a container fallback, before FoamStudio can run a solver. OpenFOAM stays an external process. `wsl.exe` expands `$` in its arguments. The WSL `/tmp` directory does not survive from one `wsl.exe` call to the next. Docker has a Python SDK, and SSH has paramiko, but neither is required to launch a process.

### Decision

WSL commands are scripts inside the case directory, with LF endings and a `chmod +x` step. FoamStudio does not put `$` on a `wsl.exe` argument list. Paths translate both ways between `C:\` and `/mnt/c`. `:Zone.Identifier` files are removed before a run. Docker is the `docker` CLI. ESI images use `/usr/lib/openfoam/openfoam<ver>/etc/bashrc`. A `latest` tag is ignored because it has no version. Foundation images are accepted only when the repository is `openfoam/openfoam<N>` and the tag is that same number. SSH stays Phase 8.

### Consequences

Phase 1 adds no paramiko, asyncssh, or Docker SDK dependency. A case path that contains `$` is refused for WSL and Docker. The runtime wizard can show an install command and open it in a visible terminal; it does not hide a failing command.

## ADR-0005: Node is the headless generator host

Date: 2026-10-27
Status: accepted

### Context

`tests/headless.js` loads `openfoam_case_generator.html` and the golden files in `tests/golden` were produced by that Node process. The plan allows bundling a small Node runtime or running the same script on QuickJS. A second engine can change number formatting or key order and break the byte-identity check. Phase 2 needs a headless path for `foamstudio --write-case` and for CI machines that are not running Qt WebEngine.

### Decision

Node remains the headless host. `foamstudio/generator/headless.py` shells out to `node tests/headless.js`. The page script stays the only dictionary writer. QuickJS and a bundled Node runtime are not added. If `node` is missing, the failure names that command and tells the user to install Node.js 20 or newer. `FOAMSTUDIO_NODE` selects the executable when it is not on `PATH`.

### Consequences

CLI, batch, and the 25-solver acceptance test depend on Node. The WebEngine bridge is a second host for the same HTML file, checked against the same golden files. `GEN_VERSION` stays 2.2.0.

## ADR-0006: Phase 2 uses the PySide6 WebEngine wheel

Date: 2026-10-27
Status: accepted

### Context

Qt WebEngine is not in the PySide6 Essentials wheel. Through 6.11 it shipped inside `PySide6_Addons` together with Qt Charts and Qt Data Visualization. PySide6 6.12 moved Qt WebEngine into `PySide6_WebEngine`. Addons still provides Qt WebChannel, and it still contains Charts and Data Visualization. The plan lists Qt WebEngine as LGPL-3 and says to avoid those GPL-only Qt add-ons. FoamStudio is GPL-3.0-only, so a GPL-3 module would be allowed, but Charts and Data Visualization are still out of scope. The Addons wheel reports `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. The audit selects the LGPL-3.0-only alternative. The WebEngine wheel is audited the same way.

### Decision

Phase 2 depends on `PySide6_Addons` and `PySide6_WebEngine` at the same Qt release as `PySide6_Essentials`. The WebEngine wheel may add a build suffix (`6.12.0.140` beside `6.12.0`). The test compares the first three version components. The setup panel imports Qt WebEngine and Qt WebChannel. The application does not import Qt Charts or Qt Data Visualization. `packaging/foamstudio.spec` hidden-imports WebEngine and WebChannel, collects the generator HTML and `tests/headless.js`, and keeps Charts and Data Visualization in `excludes`. A full PyInstaller build is gated by `FOAMSTUDIO_PYINSTALLER=1`. The default test checks that the installed tree contains `QtWebEngineProcess`, `icudtl.dat`, and `qtwebengine_resources.pak`.

### Consequences

The install is larger. WebEngine is not created during `--self-test` or when `FOAMSTUDIO_HEADLESS=1`. The byte-identity bridge test runs in a process that is allowed a display (xvfb on Linux CI) because the offscreen Qt platform does not host Chromium. Remote script tags in the HTML are removed before the page loads, so generation does not wait on a CDN.

## ADR-0007: SSH uses the OpenSSH client

Date: 2026-10-27
Status: accepted

### Context

Phase 8 needs a remote runtime, file sync, and SLURM/PBS text. asyncssh is EPL-2.0, which the licence audit does not accept. paramiko is LGPL-2.1-only and would be allowed, but it is a second SSH implementation. Docker already uses the `docker` CLI for the same reason: one well-known program, no extra library.

NumPy 2.5 reports `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`. An SPDX `AND` requires every clause. CC0-1.0 is a public-domain dedication and is GPL-3 compatible, so the audit allow-list includes `cc0`.

### Decision

SSH and scp are the system OpenSSH client with `BatchMode=yes`. Host, user, remote path, and bashrc must not contain `$`. The remote bash script may, because it is one argument and the local shell does not expand it. `detect()` does not scan SSH unless a record is configured. SLURM and PBS are script templates. trame is an optional script the user runs; it is not a dependency.

### Consequences

No asyncssh and no paramiko. An integration test needs `FOAMSTUDIO_SSH_INTEGRATION=1` and was not run here. CC0 stays on the allow-list for NumPy's compound expression.

## ADR-0008: The 3D view waits for a successful import

Date: 2026-10-27
Status: accepted

### Context

Phase 3 adds PyVista. The offscreen test suite forces `QT_QPA_PLATFORM=offscreen`. A PyVista widget at startup can fail that platform, and the shell test requires the centre widget to stay the "No geometry loaded." label with the six tree labels.

### Decision

Startup keeps that label. Tree clicks swap the properties dock. `import_geometry` builds `Viewer3D` and replaces the centre widget only after the file parses. PyVista and pyvistaqt import only when `FOAMSTUDIO_VIEWER=1`. Slice, clip, iso-lines, and streamlines live in `core/post/filters.py` and do not import VTK.

### Consequences

Headless and `--self-test` never construct a plotter. A display is required before the 3D widget is claimed to work.

## ADR-0009: foamlib reads fields and does not write solver dictionaries

Date: 2026-10-27
Status: accepted

### Context

foamlib is GPL-3.0 and can parse OpenFOAM files. The plan says the HTML generator remains the only solver-dictionary writer. Duplicating that writer in Python would fork `GEN_VERSION`.

### Decision

`core/post/fields.py` parses ASCII `internalField` text. If foamlib can open the same file, the source tag becomes `foamlib` and the values stay the ASCII parse. foamlib is not called to write the 25 solver dictionaries. Mesh dictionaries (`blockMeshDict`, `snappyHexMeshDict`) are separate builders in `core/mesh`.

### Consequences

A foamlib write API is out of scope. Field tests accept either source tag as long as the numbers match.

## ADR-0010: Crash upload is off unless three switches agree

Date: 2026-10-27
Status: accepted

### Context

Phase 9 asks for telemetry off by default and an opt-in crash report. A handler that POSTs on every exception would send stack traces without a decision.

### Decision

The crash file is always written locally. `maybe_upload` returns no plan when crash reports are off, and it does not open a socket. A POST runs only when the setting or `FOAMSTUDIO_CRASH_REPORTS=1` is on, `FOAMSTUDIO_CRASH_URL` is set, and `FOAMSTUDIO_CRASH_UPLOAD=1`. The update feed parser does nothing until a channel is configured. Partial rollout uses `update_allowed`.

### Consequences

Tests must not set `FOAMSTUDIO_CRASH_UPLOAD`. There is no default upload URL.

## ADR-0011: Installers are scripts until a signed build exists

Date: 2026-10-27
Status: accepted

### Context

Phase 9 lists Inno Setup or MSIX, a dmg, an AppImage, a Flatpak, signing, and a 15-minute fresh-machine test. This working tree has no signing certificate and was not built on a fresh VM. PyInstaller stays gated because a one-folder WebEngine build is large.

### Decision

`packaging/` holds the Inno script, MSIX notes, `make-dmg.sh`, `make-appimage.sh`, a Flatpak manifest, and `sign.ps1`. `sign.ps1` exits 2 when `FOAMSTUDIO_SIGN_PFX` is unset. `packaging/FRESH_VM.md` is the timing sheet and it records that the test was not run. The application version for this phase set is 0.9.0, not 1.0.

### Consequences

Do not describe GitHub CI, notarisation, or the fresh-machine clock as passed until those runs exist. Docs are an MkDocs Material site under `docs/`.

