"""Live SSH runtime check against a real sshd (localhost on the CI runner).

The Linux `runtime` job starts sshd, authorises a fresh key for the runner user,
installs ESI OpenFOAM 2412, and sets FOAMSTUDIO_SSH_INTEGRATION=1.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import subprocess
import sys
from pathlib import Path

import pytest

from foamstudio.core.runtime import bind
from foamstudio.core.runtime.model import Installation
from foamstudio.core.runtime.ssh import pull_argv, push_argv

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("FOAMSTUDIO_SSH_INTEGRATION") != "1",
        reason="set FOAMSTUDIO_SSH_INTEGRATION=1 with a reachable sshd",
    ),
    pytest.mark.skipif(sys.platform != "linux", reason="the SSH job runs on Linux"),
]

BASHRC = "/usr/lib/openfoam/openfoam2412/etc/bashrc"


def test_ssh_push_run_pull(tmp_path: Path) -> None:
    local = tmp_path / "case"
    local.mkdir()
    (local / "marker.txt").write_text("push\n", encoding="utf-8")
    remote = tmp_path / "remote"
    remote.mkdir()
    remote_case = str(remote / "case")
    installation = Installation(
        kind="ssh",
        flavour="esi",
        version="2412",
        bashrc=BASHRC,
        host=os.environ.get("FOAMSTUDIO_SSH_HOST", "localhost"),
        user=os.environ.get("FOAMSTUDIO_SSH_USER", getpass.getuser()),
        remote_case=remote_case,
    )

    push = subprocess.run(list(push_argv(installation, str(local), str(remote))), check=False)
    assert push.returncode == 0
    assert (remote / "case" / "marker.txt").is_file()

    result = asyncio.run(
        bind(installation).run("simpleFoam -help > log.help 2>&1", local, timeout=120)
    )
    assert result.returncode == 0
    assert "simpleFoam" in (remote / "case" / "log.help").read_text(encoding="utf-8")

    back = tmp_path / "back"
    pull = subprocess.run(list(pull_argv(installation, remote_case, str(back))), check=False)
    assert pull.returncode == 0
    assert (back / "log.help").is_file()
