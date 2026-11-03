"""First-install helpers: venv + libraries, OpenFOAM in WSL, manual folder pick."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

from foamstudio.core.paths import state_dir
from foamstudio.core.runtime.install_offers import _ESI_APT, install_offers
from foamstudio.core.runtime.model import Installation
from foamstudio.core.runtime.native import classify_bashrc
from foamstudio.core.runtime.paths import launch_env, unc_to_wsl
from foamstudio.core.runtime.probe import SubprocessProbe

logger = logging.getLogger("foamstudio.setup")
Log = Callable[[str], None]
DISTRO = "Ubuntu-24.04"


def venv_dir() -> Path:
    return state_dir() / "venv"


def venv_python() -> Path:
    sub = ("Scripts", "python.exe") if sys.platform == "win32" else ("bin", "python")
    return venv_dir().joinpath(*sub)


def requirements() -> tuple[str, ...]:
    try:
        reqs = metadata.requires("foamstudio") or []
    except metadata.PackageNotFoundError:  # source checkout, not pip-installed
        toml = Path(__file__).parents[2] / "pyproject.toml"
        reqs = tomllib.loads(toml.read_text())["project"]["dependencies"]
    return tuple(r for r in reqs if "extra ==" not in r)


def req_name(req: str) -> str:
    return re.split(r"[<>=!~;\[ ]", req, maxsplit=1)[0]


def check_libs(python: Path | None = None) -> list[tuple[str, str | None]]:
    """(requirement, installed version or None) for each library, in `python`."""
    py = python or (venv_python() if venv_python().is_file() else Path(sys.executable))
    names = [req_name(r) for r in requirements()]
    code = (
        "import json,sys,importlib.metadata as m\n"
        "def v(n):\n try: return m.version(n)\n except Exception: return None\n"
        "print(json.dumps([v(n) for n in sys.argv[1:]]))"
    )
    out = subprocess.run([str(py), "-c", code, *names], capture_output=True, text=True, check=False)
    found = json.loads(out.stdout) if out.returncode == 0 else [None] * len(names)
    return list(zip(requirements(), found, strict=True))


def run_streamed(argv: list[str], log: Log) -> int:
    global _current
    log("$ " + " ".join(argv))
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=launch_env(),
            start_new_session=sys.platform != "win32",
        )
    except FileNotFoundError:
        log(f"{argv[0]} not found.")
        return 127
    _current = proc
    assert proc.stdout is not None
    for raw in proc.stdout:
        # ponytail: wsl.exe prints UTF-16; stripping NULs is enough for its ASCII text
        line = raw.replace(b"\x00", b"").decode("utf-8", "replace").rstrip()
        if line:
            log(line)
    code = proc.wait()
    _current = None
    log(f"exit {code}")
    return code


_current: subprocess.Popen[bytes] | None = None


def cancel() -> None:
    """Kill the running setup step and its children."""
    proc = _current
    if proc is None or proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        import os
        import signal

        os.killpg(proc.pid, signal.SIGTERM)


LOCK = Path(__file__).with_name("requirements.lock")


def relaunch_in_venv(argv: list[str]) -> int | None:
    """Re-run FoamStudio under the managed venv (source checkout only). None = carry on here."""
    py = venv_python()
    root = Path(__file__).parents[2]
    if (
        os.environ.get("FOAMSTUDIO_NO_RELAUNCH")
        or not py.is_file()
        or not (root / "pyproject.toml").is_file()
        or Path(sys.prefix).resolve() == venv_dir().resolve()
    ):
        return None
    env = {**os.environ, "FOAMSTUDIO_NO_RELAUNCH": "1", "PYTHONPATH": str(root)}
    return subprocess.call([str(py), "-m", "foamstudio", *argv], env=env)


def install_venv(log: Log, missing_only: bool = False) -> bool:
    if getattr(sys, "frozen", False):
        log("Installed build: Python and every library ship inside FoamStudio.")
        return True
    py = venv_python()
    if not py.is_file() and run_streamed([sys.executable, "-m", "venv", str(venv_dir())], log):
        return False
    reqs = [r for r, v in check_libs(py) if v is None] if missing_only else list(requirements())
    if not reqs:
        log("All libraries already installed.")
        return True
    run_streamed([str(py), "-m", "pip", "install", "-U", "pip"], log)
    # tested versions first; the lock pins transitive deps too
    pins = ["-c", str(LOCK)] if LOCK.is_file() else []
    return run_streamed([str(py), "-m", "pip", "install", *pins, *reqs], log) == 0


def update_source(log: Log) -> bool:
    """git checkout: fast-forward pull, then top up the venv. Releases: point at GitHub."""
    root = Path(__file__).parents[2]
    if not (root / ".git").exists():
        log("Not a git checkout. Download the latest release from GitHub.")
        return False
    if run_streamed(["git", "-C", str(root), "pull", "--ff-only"], log):
        return False
    return install_venv(log, missing_only=True)


def manual_venv_commands() -> str:
    reqs = " ".join(f'"{r}"' for r in requirements())
    return f'{sys.executable} -m venv "{venv_dir()}"\n"{venv_python()}" -m pip install {reqs}'


def manual_openfoam_commands() -> str:
    return "\n\n".join(f"# {o.title}\n{o.command}" for o in install_offers(sys.platform))


def install_openfoam(log: Log) -> bool:
    """Windows: WSL Ubuntu (root, no prompts) + ESI 2412 apt. Elsewhere sudo needs a terminal."""
    if sys.platform != "win32":
        log("Auto-install needs sudo; run this in a terminal:\n" + manual_openfoam_commands())
        return False
    try:
        listed = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, check=False)
    except FileNotFoundError:
        return _docker_fallback(log)
    if DISTRO not in listed.stdout.replace(b"\x00", b"").decode("utf-8", "replace"):
        if run_streamed(["wsl.exe", "--install", "-d", DISTRO, "--no-launch"], log):
            log("WSL install failed. Reboot if Windows asked; setup resumes on next launch.")
            return _docker_fallback(log)
        if run_streamed(["ubuntu2404.exe", "install", "--root"], log):
            log("Ubuntu registration failed. Reboot, then run setup again.")
            return False
    return (
        run_streamed(["wsl.exe", "-d", DISTRO, "-u", "root", "--", "bash", "-lc", _ESI_APT], log)
        == 0
    )


def _docker_fallback(log: Log) -> bool:
    import shutil

    if shutil.which("docker") is None:
        log("No WSL and no Docker. Install Docker Desktop or enable WSL, then rerun setup.")
        return False
    log("WSL unavailable: pulling the Docker image instead.")
    return run_streamed(["docker", "pull", "opencfd/openfoam-run:2412"], log) == 0


def wsl_projects_dir(distro: str) -> Path | None:
    """`\\\\wsl.localhost\\<distro>\\<home>\\foamstudio`, so cases live on the Linux disk."""
    try:
        done = SubprocessProbe().run(
            ("wsl.exe", "-d", distro, "--", "printenv", "HOME"), timeout=15
        )
    except (OSError, TimeoutError):
        return None
    home = done.stdout.strip()
    if done.returncode or not home.startswith("/"):
        return None
    path = Path(f"\\\\wsl.localhost\\{distro}{home.replace('/', chr(92))}\\foamstudio")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return path


def installation_from_folder(folder: str) -> Installation:
    """OpenFOAM root picked by hand (`<root>/etc/bashrc`); WSL roots come as UNC paths."""
    bashrc = Path(folder) / "etc" / "bashrc"
    if not bashrc.is_file():
        raise ValueError(f"No etc/bashrc under {folder}. Pick the OpenFOAM root folder.")
    distro, linux = "", bashrc.as_posix()
    if folder.replace("\\", "/").startswith("//wsl"):
        distro, linux = unc_to_wsl(str(bashrc))
    elif sys.platform == "win32":
        raise ValueError("On Windows pick the folder through \\\\wsl.localhost\\<distro>\\...")
    kind = classify_bashrc(linux)
    if kind is None:
        match = re.search(r"WM_PROJECT_VERSION=(\S+)", bashrc.read_text(errors="replace"))
        if match is None:
            raise ValueError(f"{bashrc} does not set WM_PROJECT_VERSION.")
        ver = match.group(1).strip("'\"")
        kind = ("esi", ver[1:]) if ver.startswith("v") else ("foundation", ver)
    return Installation(
        kind="wsl" if distro else "native",
        flavour=kind[0],
        version=kind[1],
        bashrc=linux,
        distro=distro,
    )
