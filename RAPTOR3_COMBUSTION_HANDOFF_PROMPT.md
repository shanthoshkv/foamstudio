# Handoff prompt: Raptor 3 combustion CFD

Paste everything below the line into Claude Code, opened in the root of this repo, on the new PC.

---

You are continuing a Raptor 3 combustion CFD study that a previous Claude Code session started on
my laptop. Pick up exactly where it stopped. Read these first, fully, before doing anything:

1. `raptor 3 combustion cfd.md` (repo root): the full record. Inputs, sources, preburner model,
   chemistry reduction and validation, the chemistry-solver findings, case setup, boundary
   conditions, run history, next steps, limitations.
2. `scripts/raptor_chem.py`, `scripts/raptor_comb.py`, `scripts/nozzle_cfd.py`,
   `scripts/nozzle_init.py`, `scripts/nozzle_post.py`, and the `solvers/raptor3_comb_*` scripts.
3. `docs/validation.md`, section "Raptor 3 sea-level nozzle and plume" (the earlier non-reacting
   study this builds on; same geometry).

Do not redo what is already settled: the preburner model (Tc 3787 K vs CEA 3783 K), the 28-species
DRG mechanism, the NASA-7 6000 K refit, the chemkinToFoam fixes, and the chemistry solver choice
(EulerImplicit with equilibriumRateLimiter on; seulex/Rosenbrock stall at 350 bar; TDAC aborts with
EulerImplicit). Do not re-run the web research unless something is missing.

## New machine

AMD Ryzen 9 9950X3D (16 cores / 32 threads), RTX 5080 16 GB, 32 GB RAM, Windows. OpenFOAM's
reactingFoam is CPU-only: run on 16 MPI ranks (physical cores). The GPU is only useful for
rendering frames.

## Step 0: environment (check first, install only what is missing)

- WSL2 Ubuntu 24.04 with OpenFOAM ESI **v2412** at `/usr/lib/openfoam/openfoam2412`
  (`apt` package `openfoam2412-default` from the openfoam.com repository), plus `ffmpeg`.
  Give WSL enough memory in `%UserProfile%\.wslconfig` (e.g. `memory=24GB`, `processors=32`).
- Windows Python 3.12 (`py -3.12`) with `cantera` (3.1), `numpy`, `matplotlib`, `rocketcea`.
- Repo `.venv` (Python 3.12) with `pyvista`, `matplotlib`, `numpy` for post-processing and frames.
- Ask me before installing anything system-wide (WSL distro, OpenFOAM, .wslconfig).
- Git Bash mangles `\\wsl.localhost\...` paths (a stray `C:\wsl.localhost\` folder appeared on
  the laptop). Run the case writer from PowerShell, or with `MSYS_NO_PATHCONV=1`.

## Step 1: rebuild and time

1. `py -3.12 scripts/raptor_chem.py solvers/raptor3_chem` only if the mechanism files are
   missing or you change the chemistry (they are committed).
2. PowerShell, repo root: `.\solvers\raptor3_comb_rebuild.ps1` (writes
   `~/foamstudio/nozzles/raptor3-comb` in WSL, meshes, splits the injector patches, converts the
   chemistry, initialises the 1-D field). Expect `pre-ok` and `initialised 64000 nozzle cells`.
3. `wsl -- bash solvers/raptor3_comb_smoke.sh 5`: serial 5-iteration timing with **PaSR**
   (untested so far). On the laptop EDC took ~127 s/iteration serial. If PaSR is still too slow
   for a run of several thousand iterations on 16 ranks, follow the fallback order in section 7
   of the md file and record what you chose and why.

## Step 2: production steady run

`wsl -- bash solvers/raptor3_comb_run.sh 16` in the background, with a monitor that reports
progress and every failure signature (FATAL, floating point exception, nan, underflow, Killed).
Converged when the faceplate area-average p (`postProcessing/pFace`) and the outlet mass flow are
flat over ~1000 iterations and ṁ_out matches ṁ_in within 0.5 %. Pc is not imposed; report it,
c* = Pc·At/ṁ and c* efficiency against CEA (1854 m/s).

## Step 3: ignition transient (close-up combustion video, a hard requirement)

I want a clear video of the combustion reaction, and one close-up video of the combustion chamber
with combustion taking place. Build it from a time-accurate ignition run as described in section 7
step 3 of the md file. The chamber starts filled with unburnt 809 K preburner-gas blend at
~350 bar, a torch-igniter hot kernel near the faceplate lights it, and the flame spreads and anchors
on the injector rings. Use ddt Euler, writes every ~5-10 µs over ~1-3 ms. Render the close-up as
4K and 1080p: temperature on one half, heat release (Qdot, log) on the mirrored half, plus separate
OH and CH4/O2 consumption views.

## Step 4: post-processing, plots, videos

- Write `scripts/raptor_comb_post.py` (pattern: `scripts/nozzle_post.py`): performance JSON
  (Pc, c*, η_c*, thrust and Isp at sea level and vacuum, exit Mach and pressure), axial profiles
  (T, p, Mach, species), combustion efficiency vs x, wall heat flux and y+, convergence history,
  chemistry validation plots from `solvers/raptor3_chem/chem-results.json`, contour stills for the
  chamber close-up and the full engine.
- Videos: the ignition close-up, full-engine field videos (T, Mach, p, Qdot, OH, CO, H2O),
  an LTS convergence animation labelled as solver iterations (not physical time), and a long-form
  narrated video of the whole study: Windows SAPI narration (`System.Speech`, voice Microsoft
  Zira) per section, matplotlib title/plot slides, ffmpeg libx264 + aac, each slide's duration set
  by its narration.

## Step 5: write-up

Update `raptor 3 combustion cfd.md` with results, then add a "Raptor 3 combustion" section to
`docs/validation.md` and a section on the website (`website/index.html`) alongside the existing
Raptor 3 nozzle videos. State clearly that this is an estimate, not validation, and keep the
limitations list.

## Working rules

- Report outcomes faithfully. If a run fails, say so with the log lines.
- Keep run artefacts (processor dirs, time dirs, frames) out of git. Commit scripts, docs, plots
  and small result JSON. Ask before pushing large videos.
- Commit on the `raptor3-combustion` branch, not master.
