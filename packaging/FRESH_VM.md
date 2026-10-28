# Fresh-machine timing test

This procedure was **not** executed on a fresh Windows 11, macOS, or Ubuntu 24.04 virtual machine. Do not record a time until someone runs it and writes the clock times below.

## Steps

1. Install from the unsigned installer, the dmg, or the AppImage. Note the clock.
2. Launch FoamStudio. Complete the runtime wizard or skip it and point at an existing OpenFOAM.
3. Open `samples/cavity` as the reference, create a project, and write the cavity case from the generator.
4. Run the solver from the Run section.
5. Open the HTML report and the ParaView state.
6. Note the clock again. The target in the plan is under 15 minutes from install to results.

## Record

| Host | Start | Results visible | Minutes | Installer build |
| --- | --- | --- | --- | --- |
| Win 11 | not run | not run |  | not built |
| macOS | not run | not run |  | not built |
| Ubuntu 24.04 | not run | not run |  | not built |

PyInstaller itself stays behind `FOAMSTUDIO_PYINSTALLER=1`. Signing stays behind `FOAMSTUDIO_SIGN_PFX`.
