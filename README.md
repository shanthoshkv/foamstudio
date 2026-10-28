# FoamStudio

Desktop GUI for the OpenFOAM workflow. It detects an OpenFOAM runtime and runs
it as an external process, and it writes a project case from the HTML case
generator. OpenFOAM is not bundled and is not linked.

FoamStudio is free software under the GNU General Public License v3.0 only.
There is no warranty. See [LICENSE](LICENSE).

The case generator in `openfoam_case_generator.html` remains the only writer of
OpenFOAM dictionaries. Its checks are unchanged: `node tests/check.js`.

## Run

```text
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\foamstudio
```

Use regular CPython 3.11 or newer. PySide6 6.12 publishes no wheels for the free-threaded build (`python3.13t`), so `py -3` is the wrong interpreter when that build is the default.

On Linux or macOS, use `.venv/bin/python` and `.venv/bin/foamstudio`.

## Checks

```text
python -m ruff check foamstudio tests scripts
python -m ruff format --check foamstudio tests scripts
python -m mypy
python -m pytest
python -m foamstudio --self-test
python scripts/license_audit.py --check --write THIRD_PARTY_LICENSES.txt
```

Set `QT_QPA_PLATFORM=offscreen` to launch without a display.
`FOAMSTUDIO_STATE_DIR` redirects settings and logs.
`FOAMSTUDIO_LANG` selects a Qt translation (`foamstudio_<lang>.qm`). English is the source language.

Hooks: `pre-commit install` after the dev extra is installed and the virtualenv is active.

## Runtimes

`python -m foamstudio --detect-runtimes` prints detected installations as JSON. Notes go to stderr.

The first launch opens the Runtime Wizard unless `FOAMSTUDIO_HEADLESS=1` is set, a runtime is already saved, or the wizard was skipped. Tools → Runtimes... opens it again. Every action shows the command it will run.

WSL commands are LF scripts inside the case. `wsl.exe` arguments do not contain `$`. Docker uses the `docker` CLI and an `opencfd/openfoam-run` image. ESI bashrc paths look like `/usr/lib/openfoam/openfoam2412/etc/bashrc`. Foundation packages use `/opt/openfoam12/etc/bashrc`.

## Projects

A project is a folder with `foamstudio.json`, `case/`, and `geometry/`. File → New project... creates it. File → Write case writes the dictionaries.

`foamstudio --write-case case.json --project DIR` does the same write and exits. It creates the project when `foamstudio.json` is missing. The writer is `openfoam_case_generator.html`, hosted by Node (`tests/headless.js`) or by Qt WebEngine. Written files land under `case/`. `foamstudio.json` records the command.

Headless and `--self-test` leave the generator view closed. The WebEngine byte-identity check needs a display or xvfb and `FOAMSTUDIO_WEBENGINE=1`.

## Batch actions

```text
foamstudio --project DIR --import-geometry part.stl --block-mesh box
foamstudio --project DIR --report report.html
foamstudio --project DIR --runtime runtime.json --run-case
foamstudio --project DIR --runtime runtime.json --matrix --run-case
```

`--matrix` queues `./Allrun`. `tests/runtests.sh` is still the solver matrix. `--report` writes HTML even when `case/log.solver` is missing, and it prints that gap on stderr.

## Layout

`foamstudio/app` is the Qt shell. `foamstudio/core` has no Qt imports.
`foamstudio/core/runtime` detects native, WSL, Docker, and SSH (OpenSSH) installations.
`foamstudio/core/geometry` imports surfaces. `foamstudio/core/mesh` writes mesh dictionaries.
`foamstudio/core/jobs.py` tracks Allrun steps. `foamstudio/core/post` reads fields and writes reports.
`foamstudio/generator` calls the HTML writer for solver dictionaries.
The centre view stays "No geometry loaded." until File → Import geometry... succeeds.
Decisions are in [docs/DECISIONS.md](docs/DECISIONS.md). The user guide is [docs/user-guide.md](docs/user-guide.md). The build plan is [plan.md](plan.md).

Version 0.9.0 is the local phase 3–9 tree. It is not a signed 1.0 release. See [CHANGELOG.md](CHANGELOG.md) and [packaging/FRESH_VM.md](packaging/FRESH_VM.md).
