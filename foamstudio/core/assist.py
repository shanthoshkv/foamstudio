"""Small user-facing helpers: error hints, pre-run checks, git snapshots, support bundle."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from foamstudio.core.paths import log_dir

# (pattern in a FOAM FATAL log, plain-English fix)
_HINTS = (
    (r"Cannot find patchField entry for (\w+)", "Add a boundaryField entry for patch '{0}' in 0/."),
    (
        r"cannot find file\s+\"?([^\s\"]+)",
        "Missing file {0}. Write the case again or check the path.",
    ),
    (
        r"keyword (\w+) is undefined",
        "Dictionary keyword '{0}' is missing. Add it (see the tutorial).",
    ),
    (
        r"Maximum number of iterations exceeded",
        "Linear solver stalled: lower relaxation or deltaT.",
    ),
    (
        r"sigFpe|Floating point exception",
        "Solution diverged: smaller deltaT, lower relaxation, check BCs.",
    ),
    (
        r"Courant Number mean: \S+ max: (\d{2,}\.?\d*)",
        "Courant max {0}: reduce deltaT or enable adjustTimeStep.",
    ),
    (
        r"negative (?:initial )?temperature|Negative temperature",
        "Negative T: check thermo BCs and lower relaxation.",
    ),
    (r"Unknown patchField type (\w+)", "BC type '{0}' does not exist in this OpenFOAM version."),
    (
        r"Unable to set reference cell",
        "Pressure needs a reference: pRefCell/pRefValue or a fixedValue p patch.",
    ),
    (
        r"bad allocation|std::bad_alloc",
        "Out of memory: fewer cells, more ranks, or raise WSL memory.",
    ),
)


def explain_foam_error(log: str) -> str:
    for pattern, fix in _HINTS:
        match = re.search(pattern, log, re.IGNORECASE)
        if match:
            return fix.format(*match.groups())
    return ""


def _names(text: str, block: str) -> set[str]:
    """Top-level entry names inside `block { ... }` of an OpenFOAM dict (comments ignored)."""
    text = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))
    start = re.search(rf"\b{block}\b\s*(?:\d+\s*)?[({{]", text)
    if not start:
        return set()
    depth, names, i, token = 1, set(), start.end(), ""
    while i < len(text) and depth:
        ch = text[i]
        if ch in "{(":
            if depth == 1 and token.strip():
                names.add(token.strip().split()[-1].strip('"'))
            depth += 1
            token = ""
        elif ch in "})":
            depth -= 1
            token = ""
        elif ch == ";" and depth == 1:
            token = ""
        elif depth == 1:
            token += ch
        i += 1
    return names


def validate_case(case: Path) -> list[str]:
    """Patches in polyMesh/boundary that a 0/ field does not cover (regex patches skipped)."""
    boundary = case / "constant" / "polyMesh" / "boundary"
    zero = case / "0" if (case / "0").is_dir() else case / "0.orig"
    if not boundary.is_file() or not zero.is_dir():
        return []
    text = re.sub(r"FoamFile\s*{[^}]*}", "", boundary.read_text(errors="replace"))
    patches = _names("b(" + text.split("(", 1)[-1], "b") if "(" in text else set()
    problems = []
    for field in sorted(p for p in zero.iterdir() if p.is_file() and not p.name.startswith(".")):
        body = field.read_text(errors="replace")
        if "boundaryField" not in body:
            continue
        have = _names(body, "boundaryField")
        if any(n.startswith(('"', ".*")) or "*" in n or "|" in n for n in have):
            continue
        for patch in sorted(patches - have):
            problems.append(f"0/{field.name}: no entry for patch '{patch}'")
    return problems


_GITIGNORE = "processor*/\n[1-9]*/\n0.[0-9]*/\npostProcessing/\n*.foam\nlog.*\n.foamstudio/\n"


def git_snapshot(case: Path, message: str) -> str:
    """Commit the case setup (not results) so each run traces to its inputs. '' if no git."""
    git = shutil.which("git")
    if git is None:
        return ""

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [git, "-C", str(case), *args], capture_output=True, text=True, check=False
        )

    if not (case / ".git").exists():
        run("init", "-q")
        (case / ".gitignore").write_text(_GITIGNORE)
    run("add", "-A")
    done = run(
        "-c",
        "user.name=FoamStudio",
        "-c",
        "user.email=foamstudio@localhost",
        "commit",
        "-q",
        "-m",
        message,
    )
    return run("rev-parse", "--short", "HEAD").stdout.strip() if done.returncode == 0 else ""


def wsl_health(distro: str) -> list[str]:
    def out(*argv: str) -> str:
        try:
            done = subprocess.run(list(argv), capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return str(exc)
        return done.stdout.replace(b"\x00", b"").decode("utf-8", "replace").strip()

    cfg = Path.home() / ".wslconfig"
    return [
        "# wsl -l -v",
        out("wsl.exe", "-l", "-v"),
        "# disk",
        out("wsl.exe", "-d", distro, "--", "df", "-h", "/"),
        "# memory",
        out("wsl.exe", "-d", distro, "--", "free", "-h"),
        "# cpus",
        out("wsl.exe", "-d", distro, "--", "nproc"),
        f"# {cfg}",
        cfg.read_text() if cfg.is_file() else "(none: WSL uses 50% of RAM)",
    ]


def support_bundle(dest: Path) -> Path:
    """Zip logs + system info for a bug report. No case files."""
    path = dest / f"foamstudio-report-{datetime.now():%Y%m%d-%H%M%S}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for log in log_dir().glob("*.log*"):
            zf.write(log, log.name)
        zf.writestr(
            "system.txt", f"{platform.platform()}\nPython {sys.version}\n{sys.executable}\n"
        )
    return path


def vscode_argv(case: Path) -> list[str]:
    from foamstudio.core.runtime.paths import unc_to_wsl

    code = shutil.which("code") or "code"
    text = str(case)
    if text.replace("\\", "/").startswith("//wsl"):
        distro, linux = unc_to_wsl(text)
        return [code, "--remote", f"wsl+{distro}", linux]
    return [code, text]
