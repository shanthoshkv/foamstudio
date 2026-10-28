"""Find ESI and Foundation bashrc files on this machine."""

from __future__ import annotations

import os
import re
from pathlib import Path

from foamstudio.core.runtime.model import Installation

_SKIP = {".git", "platforms", "build", "node_modules", "__pycache__"}
_ESI_PACKAGED = re.compile(r"/openfoam/openfoam(\d{4})/etc/bashrc$")
_ESI_TREE = re.compile(r"/OpenFOAM-v(\d{4})/etc/bashrc$")
_ESI_APP = re.compile(r"/OpenFOAM-v(\d{4})\.app/.*/etc/bashrc$")
_FOUNDATION_PACKAGED = re.compile(r"/openfoam(\d{1,2})/etc/bashrc$")
_FOUNDATION_TREE = re.compile(r"/OpenFOAM-(\d{1,2})/etc/bashrc$")
_FOUNDATION_APP = re.compile(r"/OpenFOAM-(\d{1,2})\.app/.*/etc/bashrc$")


def classify_bashrc(path: str) -> tuple[str, str] | None:
    text = path.replace("\\", "/")
    for pattern, flavour in (
        (_ESI_PACKAGED, "esi"),
        (_ESI_TREE, "esi"),
        (_ESI_APP, "esi"),
        (_FOUNDATION_PACKAGED, "foundation"),
        (_FOUNDATION_TREE, "foundation"),
        (_FOUNDATION_APP, "foundation"),
    ):
        match = pattern.search(text)
        if match is not None:
            return flavour, match.group(1)
    return None


def default_native_roots() -> tuple[Path, ...]:
    home = Path.home()
    return (
        Path("/usr/lib/openfoam"),
        Path("/opt"),
        Path("/usr/local/opt"),
        Path("/Applications"),
        home / "OpenFOAM",
        home / "Applications",
    )


def detect_native(roots: tuple[Path, ...] | None = None) -> tuple[Installation, ...]:
    found: list[Installation] = []
    seen: set[str] = set()
    for root in roots if roots is not None else default_native_roots():
        for bashrc in _bashrcs(root):
            kind = classify_bashrc(bashrc.as_posix())
            if kind is None:
                continue
            flavour, version = kind
            key = bashrc.as_posix()
            if key in seen:
                continue
            seen.add(key)
            found.append(
                Installation(
                    kind="native",
                    flavour=flavour,
                    version=version,
                    bashrc=key,
                )
            )
    return tuple(found)


def _bashrcs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    found: list[Path] = []
    for current, dirnames, filenames in os.walk(root):
        relative = Path(current).relative_to(root)
        depth = len(relative.parts)
        if depth > 6:
            dirnames.clear()
            continue
        dirnames[:] = [name for name in dirnames if name not in _SKIP and _descend(name)]
        if Path(current).name == "etc" and "bashrc" in filenames:
            found.append(Path(current) / "bashrc")
    return found


def _descend(name: str) -> bool:
    lowered = name.lower()
    if lowered in {"contents", "resources", "etc"}:
        return True
    return lowered.startswith("openfoam")
