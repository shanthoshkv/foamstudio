"""Locate Qt WebEngine files that a one-folder bundle has to ship.

Qt Charts and Qt Data Visualization are not part of this lookup. They stay out of the app.
"""

from __future__ import annotations

from pathlib import Path

_PROCESS_NAMES = ("QtWebEngineProcess.exe", "QtWebEngineProcess")
_PROCESS_RELATIVE = (
    "QtWebEngineProcess.exe",
    "QtWebEngineProcess",
    "Qt/libexec/QtWebEngineProcess.exe",
    "Qt/libexec/QtWebEngineProcess",
    "libexec/QtWebEngineProcess.exe",
    "libexec/QtWebEngineProcess",
)


class WebEngineResourceError(Exception):
    def __init__(self, message: str, *, suggestion: str) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"{message}\n\n{suggestion}")


def pyside_root() -> Path:
    try:
        import PySide6
    except ImportError as exc:
        raise WebEngineResourceError(
            "PySide6 is not installed.",
            suggestion='pip install "PySide6_Essentials>=6.8,<7" "PySide6_Addons>=6.8,<7"',
        ) from exc
    return Path(PySide6.__file__).resolve().parent


def webengine_files(root: Path | None = None) -> dict[str, Path]:
    folder = pyside_root() if root is None else root
    process = _first(folder, _PROCESS_RELATIVE, _PROCESS_NAMES)
    icu = _first(folder, ("resources/icudtl.dat", "Qt/resources/icudtl.dat"), ("icudtl.dat",))
    pak = _first(
        folder,
        ("resources/qtwebengine_resources.pak", "Qt/resources/qtwebengine_resources.pak"),
        ("qtwebengine_resources.pak",),
    )
    missing = [
        name
        for name, path in (
            ("QtWebEngineProcess", process),
            ("icudtl.dat", icu),
            ("qtwebengine_resources.pak", pak),
        )
        if path is None
    ]
    if process is None or icu is None or pak is None:
        raise WebEngineResourceError(
            f"Qt WebEngine resources are missing in {folder}: {', '.join(missing)}.",
            suggestion=(
                'pip install "PySide6_Addons>=6.8,<7" "PySide6_WebEngine>=6.8,<7" '
                "at the same version as PySide6_Essentials. "
                "Qt Charts and Qt Data Visualization are not required."
            ),
        )
    return {"process": process, "icudtl": icu, "resources_pak": pak}


def _first(root: Path, relative: tuple[str, ...], names: tuple[str, ...]) -> Path | None:
    for rel in relative:
        candidate = root / rel
        if candidate.is_file():
            return candidate
    for name in names:
        match = next((path for path in root.rglob(name) if path.is_file()), None)
        if match is not None:
            return match
    return None
