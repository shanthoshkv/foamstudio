"""WebEngine acceptance. Skipped unless FOAMSTUDIO_WEBENGINE=1.

The Linux CI job sets that variable and runs under xvfb. A skip here is not a pass
on that job. Offscreen Qt cannot host Chromium, so the check runs in a child process
with the platform plugin left to Qt.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


def test_bridge_twenty_five_solvers_match_golden() -> None:
    if os.environ.get("FOAMSTUDIO_WEBENGINE") != "1":
        pytest.skip("Set FOAMSTUDIO_WEBENGINE=1 to run the Qt WebEngine byte-identity check.")
    env = os.environ.copy()
    if env.get("QT_QPA_PLATFORM") == "offscreen":
        env.pop("QT_QPA_PLATFORM")
    env.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    env.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, str(_REPO / "tests" / "bridge_check.py")],
        cwd=_REPO,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    assert "BRIDGE OK" in completed.stdout
