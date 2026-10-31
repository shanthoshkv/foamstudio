# Packaging

Phase 9 builds signed installers. This directory holds the PyInstaller spec.

Phase 2 collects Qt WebEngine so the setup panel can load `openfoam_case_generator.html`. The spec also ships `tests/headless.js` and `tests/gen.js` for `foamstudio --write-case`. Qt Charts and Qt Data Visualization stay excluded and are not imported.

```text
pyinstaller packaging/foamstudio.spec
```

`tests/test_packaging.py` checks that the installed PySide6 tree contains `QtWebEngineProcess`, `icudtl.dat`, and `qtwebengine_resources.pak`. A full one-folder build runs only when `FOAMSTUDIO_PYINSTALLER=1`.

Phase 9 adds installer scripts. They were not executed here.

| Path | Role |
| --- | --- |
| `windows/foamstudio.iss` | Inno Setup, unsigned |
| `windows/MSIX.md` | MSIX steps, not built |
| `macos/make-dmg.sh` | `hdiutil` dmg, macOS only, notarisation not run |
| `linux/make-appimage.sh` | exits 2 unless `FOAMSTUDIO_APPIMAGE=1` |
| `linux/org.foamstudio.FoamStudio.yml` | Flatpak manifest, not built |
| `signing/sign.ps1` | exits 2 unless `FOAMSTUDIO_SIGN_PFX` is set |
| `FRESH_VM.md` | 15-minute procedure. The table says not run |

## 2026-10-31 local build (Windows 11, Python 3.12.4, PyInstaller 6.22.3 in a separate venv)

- One-folder build: about 5.5 min, **931 MB**, trimmed to **795 MB** by dropping WebEngine devtools resources and non-English Qt translations (frozen Setup panel still loads the generator: QtWebEngineProcess started, "Case generator ready.") (`PySide6` 544 MB, `vtk.libs` 244 MB). Excluding Python modules does not drop Qt DLLs; trimming needs a DLL-level pass.
- The first build failed to launch (`foam.svg` missing): package data was not collected. The spec now uses `collect_data_files("foamstudio")`.
- Frozen `--self-test` printed `foamstudio: launched`. Frozen `--write-case samples/cavity/case.json` wrote dictionaries identical to the dev run.
- `--write-case` (CLI) needs **Node** on PATH. The GUI writes cases through Qt WebEngine and does not.
- Inno Setup was not installed on this machine, so no installer was compiled locally. `.github/workflows/release.yml` builds all three OS bundles, runs the smoke test on the frozen app, compiles the Inno installer, writes SHA256SUMS, and attests build provenance. That workflow has not run yet.
- Installers stay **unsigned** until a certificate exists (`signing/sign.ps1`).
