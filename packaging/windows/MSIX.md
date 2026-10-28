# MSIX

An MSIX package is an alternative to the Inno Setup script in `foamstudio.iss`. This tree does not build one.

Procedure, not executed here:

1. Build `pyinstaller packaging/foamstudio.spec` with `FOAMSTUDIO_PYINSTALLER=1`.
2. Create an AppxManifest that points at `dist/foamstudio/foamstudio.exe`.
3. `makeappx pack /d dist/foamstudio /p FoamStudio.msix`
4. Sign with `packaging/signing/sign.ps1`. Without `FOAMSTUDIO_SIGN_PFX` that script exits 2.

The installer must ship the GPL-3.0 licence. OpenFOAM stays outside the package.
