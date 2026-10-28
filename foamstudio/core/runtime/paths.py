"""Path translation and the case-local runner script.

wsl.exe must not see ``$VAR``: the shell text lives in a script inside the case.
``/tmp`` inside WSL is not reused between calls.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_WINDOWS = re.compile(r"^[A-Za-z]:/")


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def windows_to_wsl(path: str) -> str:
    text = path.replace("\\", "/")
    match = re.fullmatch(r"([A-Za-z]):/(.*)", text)
    if match is None:
        raise ValueError(f"Not a Windows path: {path}")
    drive = match.group(1).lower()
    rest = match.group(2)
    if rest:
        return f"/mnt/{drive}/{rest}"
    return f"/mnt/{drive}"


def wsl_to_windows(path: str) -> str:
    match = re.fullmatch(r"/mnt/([a-zA-Z])(?:/(.*))?", path)
    if match is None:
        raise ValueError(f"Not a WSL drive path: {path}")
    drive = match.group(1).upper()
    rest = match.group(2) or ""
    if rest:
        return f"{drive}:/{rest}"
    return f"{drive}:/"


def host_text(case: Path) -> str:
    """Absolute path of a case, keeping a Windows drive path un-resolved on other OS."""
    text = str(case).replace("\\", "/")
    if _WINDOWS.fullmatch(text) or _WINDOWS.match(text):
        return text[0].upper() + text[1:]
    if os.name == "nt":
        return str(case.resolve()).replace("\\", "/")
    return case.resolve().as_posix()


def bash_command(
    bashrc: str, directory: str, command: str, exports: dict[str, str] | None = None
) -> str:
    """`source <bashrc> && cd <case> && <cmd>`, with optional exports in front.

    `set -u` is intentionally absent: OpenFOAM's bashrc reads variables that are
    unset on a clean shell, and `&&` already stops the chain when a step fails.
    """
    if not command.strip():
        raise ValueError("The OpenFOAM command is empty.")
    parts: list[str] = []
    for key, value in (exports or {}).items():
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None:
            raise ValueError(f"Environment name {key!r} cannot be exported.")
        parts.append(f"export {key}={sh_quote(value)}")
    parts.append(f"source {sh_quote(bashrc)}")
    parts.append(f"cd {sh_quote(directory)}")
    parts.append(command)
    return " && ".join(parts)


def launch_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    if extra:
        env.update(extra)
    env["MSYS_NO_PATHCONV"] = "1"
    env["MSYS2_ARG_CONV_EXCL"] = "*"
    return env


def strip_zone_identifiers(case: Path) -> list[Path]:
    """Remove download-zone markers.

    On Linux those are real files whose names end with ``:Zone.Identifier``.
    On Windows the same marker is an NTFS alternate stream, which directory
    listings do not show, so each file's ``:Zone.Identifier`` stream is removed.
    """
    removed: list[Path] = []
    if not case.is_dir():
        return removed
    for path in case.rglob("*"):
        if not path.is_file():
            continue
        if path.name.endswith(":Zone.Identifier"):
            path.unlink()
            removed.append(path)
            continue
        stream = Path(str(path) + ":Zone.Identifier")
        try:
            present = stream.is_file()
        except OSError:
            present = False
        if present:
            stream.unlink()
            removed.append(stream)
    return removed


def write_runner(case: Path, body: str) -> Path:
    directory = case / ".foamstudio"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"run-{os.getpid()}-{_tick()}.sh"
    text = "#!/bin/bash\n" + body + "\n"
    if "\r" in text:
        raise ValueError("Runner script must use LF line endings.")
    path.write_bytes(text.encode("utf-8"))
    if os.name != "nt":
        path.chmod(path.stat().st_mode | 0o755)
    return path


def _tick() -> int:
    return int.from_bytes(os.urandom(4), "big")


def reject_dollar(value: str, *, what: str) -> None:
    if "$" in value:
        raise ValueError(
            f"{what} contains '$' ({value}). Rename it. wsl.exe expands '$' in its arguments."
        )
