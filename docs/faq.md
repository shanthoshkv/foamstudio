# FAQ

## WSL

`wsl.exe` expands `$` in its own arguments. FoamStudio writes an LF script in the case and passes that script path. A case path that contains `$` is refused. `:Zone.Identifier` streams are removed before a run. The wizard can show `wsl --install -d Ubuntu-24.04`. It runs that command in a visible terminal when you ask it to.

## Docker

Docker is the `docker` CLI, not a Python Docker SDK. The mount path cannot contain `$`. Image tags named `latest` are ignored because they have no version.

## Firewall and antivirus

Solver runs are normal processes (`bash`, `wsl.exe`, `docker`, `ssh`). If a run exits 127, the log names the command and points at the bashrc. If Windows Defender locks `QtWebEngineProcess` during a first launch, allow the FoamStudio folder. The app does not phone home unless crash upload is switched on.

## SSH keys

SSH uses `BatchMode=yes`, so it will not ask for a password. Load a key in the system agent first. A host name that contains `$` is refused.

## The viewer is a sentence, not a 3D window

That is the offscreen and headless path. Set `FOAMSTUDIO_VIEWER=1` on a machine with a display to construct the PyVista widget. Import is what replaces the placeholder. Clicking the project tree does not.

## Free-threaded Python

`py -3` on this development machine can be `3.13t`. PySide6 publishes no wheel for that build. Create the virtualenv with `py -3.12`.

## Can my company use FoamStudio?

FoamStudio is GPL-3.0-only. Installing and running it inside a company, including on proprietary projects, places no obligation on your cases, meshes, or results. The GPL applies when you distribute FoamStudio itself, modified or not, outside your organisation: then you must offer the source of what you ship. OpenFOAM, Gmsh, and ParaView are separate programs that FoamStudio runs as external processes. Each keeps its own licence. This is not legal advice; ask your legal team for a formal review.

## Security, SBOM, and offline use

See `SECURITY.md`. CI produces a CycloneDX SBOM and runs `pip-audit` and CodeQL. FoamStudio makes no network calls by default, so it works on an air-gapped machine once it and OpenFOAM are installed.

## Where are the solver dictionaries?

In `openfoam_case_generator.html`. `foamlib` may read an existing field file. It is not used to write those dictionaries.
