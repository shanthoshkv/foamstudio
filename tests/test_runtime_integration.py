"""Live OpenFOAM check. The fast CI matrix skips this.

The Linux `runtime` job installs ESI OpenFOAM 2412 and sets
FOAMSTUDIO_RUNTIME_INTEGRATION=1.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from foamstudio.core.runtime import bind, detect

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("FOAMSTUDIO_RUNTIME_INTEGRATION") != "1",
        reason="set FOAMSTUDIO_RUNTIME_INTEGRATION=1 to run simpleFoam -help",
    ),
    pytest.mark.skipif(
        sys.platform != "linux",
        reason="the OpenFOAM integration job runs on Linux",
    ),
]


def test_detect_finds_openfoam_and_simplefoam_help(tmp_path: Path) -> None:
    report = detect(platform="linux")
    matches = [
        item
        for item in report.installations
        if item.kind == "native" and item.flavour == "esi" and item.version == "2412"
    ]
    assert matches, (report.to_dicts(), report.notes)
    case = tmp_path / "runtime-check"
    case.mkdir()
    result = asyncio.run(bind(matches[0]).run("simpleFoam -help", case, timeout=90))
    assert result.returncode == 0
    assert "simpleFoam" in (result.stdout + result.stderr) or "Usage" in (
        result.stdout + result.stderr
    )
