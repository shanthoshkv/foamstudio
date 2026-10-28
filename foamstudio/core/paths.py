"""Log and crash-report locations.

`FOAMSTUDIO_STATE_DIR` overrides the platform directory. Tests set it so a run
never writes into the user's real application data.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def state_dir() -> Path:
    override = os.environ.get("FOAMSTUDIO_STATE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        root = Path(local) if local else Path.home() / "AppData" / "Local"
        return root / "FoamStudio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FoamStudio"
    xdg = os.environ.get("XDG_STATE_HOME")
    root = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return root / "foamstudio"


def log_dir() -> Path:
    return state_dir() / "logs"


def log_file_path() -> Path:
    return log_dir() / "foamstudio.log"


def crash_report_path() -> Path:
    return log_dir() / "crash.log"
