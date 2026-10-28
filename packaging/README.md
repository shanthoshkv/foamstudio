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
