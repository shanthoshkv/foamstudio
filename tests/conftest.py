"""Keep Qt offscreen and away from the user's FoamStudio settings."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_state = Path(tempfile.mkdtemp(prefix="foamstudio-pytest-"))
os.environ["FOAMSTUDIO_STATE_DIR"] = str(_state)
os.environ["FOAMSTUDIO_HEADLESS"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["FOAMSTUDIO_INSTANCE_KEY"] = f"foamstudio-pytest-{os.getpid()}"


def _cleanup() -> None:
    shutil.rmtree(_state, ignore_errors=True)


atexit.register(_cleanup)
