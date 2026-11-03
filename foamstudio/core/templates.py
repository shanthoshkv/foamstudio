"""Case templates from the installed OpenFOAM tutorials, user plugins, and solver patches.

OpenFOAM's own tutorials are maintained and tested by its developers, so FoamStudio starts
advanced physics (combustion, multiphase, CHT, sprays, overset, AMI, adjoint) from them rather
than from hand-written dictionaries.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from foamstudio.core.paths import state_dir
from foamstudio.core.runtime.model import Installation
from foamstudio.core.runtime.paths import windows_to_wsl


@dataclass(frozen=True)
class Template:
    key: str
    title: str
    tutorial: str  # path under <install>/tutorials (ESI layout)
    physics: str


TEMPLATES = (
    Template(
        "combustion",
        "Laminar methane flame (reactingFoam)",
        "combustion/reactingFoam/laminar/counterFlowFlame2D",
        "Combustion, Chemkin-style reactions, multi-species",
    ),
    Template(
        "vof",
        "Dam break, free surface (interFoam)",
        "multiphase/interFoam/laminar/damBreak/damBreak",
        "Multiphase VOF",
    ),
    Template(
        "cavitation",
        "Cavitating bullet (interPhaseChangeFoam)",
        "multiphase/interPhaseChangeFoam/cavitatingBullet",
        "Cavitation, Schnerr-Sauer",
    ),
    Template(
        "cht",
        "Multi-region heater (chtMultiRegionFoam)",
        "heatTransfer/chtMultiRegionFoam/multiRegionHeater",
        "Conjugate heat transfer",
    ),
    Template(
        "spray",
        "Diesel spray bomb (sprayFoam)",
        "lagrangian/sprayFoam/aachenBomb",
        "Lagrangian spray, evaporation, combustion",
    ),
    Template(
        "les",
        "Backward step LES (pisoFoam)",
        "incompressible/pisoFoam/LES/pitzDaily",
        "Large-eddy simulation",
    ),
    Template(
        "mrf",
        "Stirred vessel, rotating frame (simpleFoam + MRF)",
        "incompressible/simpleFoam/mixerVessel2D",
        "MRF rotating machinery",
    ),
    Template(
        "ami",
        "Stirred vessel, sliding mesh (pimpleFoam + AMI)",
        "incompressible/pimpleFoam/laminar/mixerVesselAMI2D/mixerVesselAMI2D",
        "Sliding mesh",
    ),
    Template(
        "propeller",
        "Propeller, rotating AMI (pimpleFoam)",
        "incompressible/pimpleFoam/RAS/propeller",
        "3D rotating machinery",
    ),
    Template(
        "periodic",
        "Periodic AMI passage (pimpleFoam)",
        "incompressible/pimpleFoam/RAS/oscillatingInletPeriodicAMI2D",
        "Rotational periodicity",
    ),
    Template(
        "cyclic",
        "Swirling pipe, cyclic (simpleFoam)",
        "incompressible/simpleFoam/pipeCyclic",
        "Periodic boundaries",
    ),
    Template(
        "rotorDisk",
        "Rotor disk actuator (simpleFoam)",
        "incompressible/simpleFoam/rotorDisk",
        "Actuator disk",
    ),
    Template(
        "overset",
        "Overset rotor (overPimpleDyMFoam)",
        "incompressible/overPimpleDyMFoam/simpleRotor",
        "Overset meshes",
    ),
    Template(
        "adjoint",
        "Adjoint shape optimisation (adjointOptimisationFoam)",
        "incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/laminar/primalAdjoint",
        "Adjoint optimisation",
    ),
    Template(
        "particles",
        "Dense particles in a rotor (MPPICDyMFoam)",
        "lagrangian/MPPICDyMFoam/denseRotor2DAMI",
        "Particle-laden flow",
    ),
)


def tutorial_root(inst: Installation) -> str:
    """<install>/tutorials, from the bashrc path (…/openfoam2412/etc/bashrc)."""
    return inst.bashrc.rsplit("/etc/bashrc", 1)[0] + "/tutorials"


def copy_template(inst: Installation, key: str, dest: Path) -> Path:
    """Copy one tutorial into dest/case (WSL: copied inside the distro; native: shutil)."""
    t = next((t for t in TEMPLATES if t.key == key), None)
    if t is None:
        raise ValueError(f"Unknown template {key!r}")
    if inst.flavour != "esi":
        raise ValueError("Templates use the ESI tutorial layout; pick an ESI runtime (v2306+).")
    src = f"{tutorial_root(inst)}/{t.tutorial}"
    target = dest / "case"
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"{target} is not empty")
    target.mkdir(parents=True, exist_ok=True)
    if inst.kind == "wsl":
        text = str(target).replace("\\", "/")
        linux = windows_to_wsl(text)
        done = subprocess.run(
            ["wsl.exe", "-d", inst.distro, "--", "cp", "-r", f"{src}/.", linux],
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode:
            raise RuntimeError(done.stderr.strip() or f"cp failed for {src}")
    elif inst.kind == "native":
        shutil.copytree(src, target, dirs_exist_ok=True)
    else:
        raise ValueError("Templates need a native or WSL runtime.")
    (dest / "template.json").write_text(json.dumps({"template": key, "source": src}, indent=2))
    return target


# ------------------------------------------------------------------ plugins
def plugin_dir() -> Path:
    return state_dir() / "plugins"


def plugins() -> list[dict[str, object]]:
    """A plugin is a folder with plugin.json: {name, description, template?: path, script?: file}."""
    found = []
    for meta in sorted(plugin_dir().glob("*/plugin.json")):
        try:
            data = json.loads(meta.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        data["path"] = str(meta.parent)
        found.append(data)
    return found


# ------------------------------------------------------------------ solver patches
PATCHES = {
    "rhoCentralFoamAxi": "solvers/build_rhoCentralFoamAxi.sh",  # wedge-aware Courant + T floor
}


def build_patched_solver(inst: Installation, name: str, repo_root: Path) -> str:
    """wmake a patched solver inside the runtime; returns the build output tail."""
    script = repo_root / PATCHES[name]
    if inst.kind != "wsl":
        argv = ["bash", str(script)]
    else:
        argv = [
            "wsl.exe",
            "-d",
            inst.distro,
            "--",
            "bash",
            windows_to_wsl(str(script).replace("\\", "/")),
        ]
    done = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=1800)
    return (done.stdout + done.stderr)[-2000:]
