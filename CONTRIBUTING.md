# Contributing

FoamStudio is GPL-3.0-only. Contributions are accepted under that licence.

## Checks

Use a regular CPython 3.11+ virtualenv (not a free-threaded build):

```text
python -m pip install -e ".[dev]"
python -m ruff check foamstudio tests scripts
python -m ruff format --check foamstudio tests scripts
python -m mypy
python -m pytest
python -m foamstudio --self-test
python scripts/license_audit.py --check --write THIRD_PARTY_LICENSES.txt
node tests/check.js
```

`QT_QPA_PLATFORM=offscreen` and `FOAMSTUDIO_HEADLESS=1` are set by `tests/conftest.py`.

## Rules that keep the generator honest

- Solver dictionaries are written only by `openfoam_case_generator.html`.
- Do not bump `GEN_VERSION` unless generator output changes, and then update `tests/golden` in the same change.
- OpenFOAM, Gmsh, and ParaView stay external processes.
- `foamstudio/core` does not import Qt.
- New dependencies that are not already in `plan.md` section 3 need an ADR first.
- `docs/DECISIONS.md` records the decision. `CHANGELOG.md` records the user-visible change.

## Tests that need a real tool

Skip unless the matching variable is `1`:

| Variable | What it unlocks |
| --- | --- |
| `FOAMSTUDIO_RUNTIME_INTEGRATION` | A real OpenFOAM `simpleFoam -help` |
| `FOAMSTUDIO_SSH_INTEGRATION` | sshd plus OpenFOAM |
| `FOAMSTUDIO_VIEWER` | PyVista widget |
| `FOAMSTUDIO_PARAVIEW` | ParaView or pvpython |
| `FOAMSTUDIO_PYINSTALLER` | One-folder build |
| `FOAMSTUDIO_CRASH_UPLOAD` | HTTP POST of a crash file |

## Discussions and bugs

Use GitHub Discussions for questions. Bug reports should include `foamstudio.json` and the log tail from the console or `log.solver`. Issue templates ask for both.
