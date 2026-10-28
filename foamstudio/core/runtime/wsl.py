"""Windows Subsystem for Linux. Commands are scripts, never inline ``$VAR``."""

from __future__ import annotations

from pathlib import Path

from foamstudio.core.runtime.model import Installation, format_argv, log_tail
from foamstudio.core.runtime.native import classify_bashrc
from foamstudio.core.runtime.paths import reject_dollar, windows_to_wsl
from foamstudio.core.runtime.probe import Completed, Probe, ProbeMissing

_LIST = ("wsl.exe", "-l", "-q")
_BASHRCS = (
    "ls -d "
    "/usr/lib/openfoam/openfoam*/etc/bashrc "
    "/opt/openfoam*/etc/bashrc "
    "/home/*/OpenFOAM/OpenFOAM-*/etc/bashrc "
    "/root/OpenFOAM/OpenFOAM-*/etc/bashrc "
    "2>/dev/null || true"
)


def parse_wsl_names(text: str) -> tuple[str, ...]:
    names: list[str] = []
    for raw in text.replace("\x00", "").splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.lower().startswith("windows subsystem"):
            continue
        name = line.replace("(Default)", "").strip()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def detect_wsl(
    probe: Probe, *, timeout: float = 15
) -> tuple[tuple[Installation, ...], tuple[str, ...]]:
    try:
        listed = probe.run(_LIST, timeout=timeout)
    except ProbeMissing as exc:
        return (), (f"{exc} Install WSL2 with: wsl --install -d Ubuntu-24.04",)
    except TimeoutError as exc:
        return (), (f"wsl.exe -l -q timed out.\n{exc}\nRestart WSL with: wsl --shutdown",)
    if listed.returncode != 0:
        return (), (_failed(listed, "Install WSL2 with: wsl --install -d Ubuntu-24.04"),)
    found: list[Installation] = []
    notes: list[str] = []
    for distro in parse_wsl_names(listed.stdout):
        installs, note = _distro(probe, distro, timeout)
        found.extend(installs)
        if note:
            notes.append(note)
    return tuple(found), tuple(notes)


def wsl_steps(distro: str, wsl_script: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    reject_dollar(distro, what="The WSL distro name")
    reject_dollar(wsl_script, what="The WSL script path")
    common = ("wsl.exe", "-d", distro, "--")
    return (
        (*common, "chmod", "+x", wsl_script),
        (*common, "bash", wsl_script),
    )


def script_mount(script: Path) -> str:
    mounted = windows_to_wsl(str(script))
    reject_dollar(mounted, what="The WSL script path")
    return mounted


def _distro(probe: Probe, distro: str, timeout: float) -> tuple[tuple[Installation, ...], str]:
    argv = ("wsl.exe", "-d", distro, "--", "bash", "-lc", _BASHRCS)
    try:
        completed = probe.run(argv, timeout=timeout)
    except ProbeMissing as exc:
        return (), str(exc)
    except TimeoutError as exc:
        return (), f"Listing OpenFOAM in {distro} timed out.\n{exc}"
    if completed.returncode != 0:
        return (), _failed(completed, f"Open {distro} and install OpenFOAM, then detect again.")
    found: list[Installation] = []
    for line in completed.stdout.splitlines():
        bashrc = line.strip()
        if not bashrc:
            continue
        kind = classify_bashrc(bashrc)
        if kind is None:
            continue
        flavour, version = kind
        found.append(
            Installation(
                kind="wsl",
                flavour=flavour,
                version=version,
                bashrc=bashrc,
                distro=distro,
            )
        )
    return tuple(found), ""


def _failed(completed: Completed, suggestion: str) -> str:
    shown = format_argv(completed.argv)
    tail = log_tail(completed.stdout, completed.stderr)
    return f"Command failed ({completed.returncode}).\n{shown}\n\n{tail}\n\n{suggestion}"
