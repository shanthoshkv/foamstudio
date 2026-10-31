"""Mesh dictionaries, the job queue, and process-tree kill arguments."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from foamstudio.core.jobs import JobQueue, allrun_commands, kill_argv
from foamstudio.core.mesh import (
    MeshFailure,
    block_mesh_dict,
    first_cell_height,
    gate,
    parse_check_mesh,
    snappy_hex_mesh_dict,
    write_gmsh_driver,
    yplus_matches,
)
from foamstudio.core.mesh.check import average_yplus
from foamstudio.core.runtime import bind
from foamstudio.core.runtime.model import Installation
from foamstudio.core.runtime.probe import Completed

_NATIVE = Installation(
    kind="native",
    flavour="esi",
    version="2412",
    bashrc="/usr/lib/openfoam/openfoam2412/etc/bashrc",
)
_WSL = Installation(
    kind="wsl",
    flavour="esi",
    version="2412",
    bashrc="/usr/lib/openfoam/openfoam2412/etc/bashrc",
    distro="Ubuntu-24.04",
)


class _Probe:
    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd=None, env=None, timeout=None):  # noqa: ANN001
        command = tuple(argv)
        self.calls.append(command)
        return Completed(command, self.returncode, self.stdout, self.stderr)


def test_block_mesh_kinds() -> None:
    box = block_mesh_dict("box")
    assert "xMin" in box and "type wall" in box and "type empty" in box
    channel = block_mesh_dict("channel", cells=(4, 2, 2))
    assert "inlet" in channel and "outlet" in channel
    assert "type empty" not in channel
    wedge = block_mesh_dict("wedge", cells=(8, 6, 9))
    assert "wedgeFront" in wedge and "type wedge" in wedge
    assert "(8 6 1)" in wedge
    with pytest.raises(MeshFailure, match="box, channel, or wedge"):
        block_mesh_dict("sphere")
    with pytest.raises(MeshFailure, match="90"):
        block_mesh_dict("wedge", angle_deg=90)


def test_yplus_estimate_and_snappy() -> None:
    height = first_cell_height(1.0, 1e-5, 1.0, 30.0)
    assert height == pytest.approx(0.005570860145311557)
    assert yplus_matches(30.0, 31.5, tolerance=0.2)
    assert yplus_matches(30.0, 40.0, tolerance=0.2) is False
    text = snappy_hex_mesh_dict("body.stl", regions=(("wake", 2),), layers=4)
    assert "body.stl" in text
    assert "wake" in text
    assert "nSurfaceLayers 4" in text
    assert f"{height:.8g}" in text


def test_gmsh_driver_rejects_dollar(tmp_path: Path) -> None:
    geo = tmp_path / "part.step"
    geo.write_text("ISO", encoding="utf-8")
    argv = write_gmsh_driver(geo, tmp_path / "out.msh", size=0.2)
    assert argv[0] == "gmsh"
    assert (tmp_path / "out.geo").is_file()
    with pytest.raises(MeshFailure, match="\\$"):
        write_gmsh_driver(tmp_path / "$bad.step", tmp_path / "out.msh")


def test_check_mesh_gate_and_yplus_log() -> None:
    ok = parse_check_mesh("Mesh non-orthogonality Max: 12\nMax skewness = 0.4\nMesh OK.\n")
    passed, _summary = gate(ok)
    assert passed
    bad = parse_check_mesh(
        "Mesh non-orthogonality Max: 80\nMax skewness = 5\nFailed 2 mesh checks\n"
    )
    assert bad.ok is False
    passed, message = gate(bad)
    assert passed is False
    assert "80" in message
    assert average_yplus("patch walls average y+: 31.5\n") == pytest.approx(31.5)


def test_job_queue_success_failure_cancel_and_matrix(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    probe = _Probe()
    queue = JobQueue(bind(_NATIVE, probe), case)
    queue.add("blockMesh")
    queue.add_matrix()
    results = queue.run_blocking(live=False)
    assert results[0].status == "succeeded"
    assert results[1].command == "./Allrun"
    assert results[1].status == "succeeded"
    assert probe.calls

    failing = JobQueue(bind(_NATIVE, _Probe(returncode=1, stderr="FOAM FATAL ERROR")), case)
    failing.add("simpleFoam")
    failed = failing.run_blocking(live=False)
    assert failed[0].status == "failed"
    assert "FOAM FATAL" in failed[0].log_tail

    cancelled = JobQueue(bind(_NATIVE, probe), case)
    cancelled.add_allrun("simpleFoam", parallel=2, mesh="none")
    cancelled.cancel()
    stopped = cancelled.run_blocking(live=False)
    assert {job.status for job in stopped} == {"cancelled"}
    commands = allrun_commands("icoFoam", parallel=4, mesh="snappyHexMesh")
    assert commands[0] == "blockMesh"
    assert "mpirun -np 4 icoFoam -parallel" in commands
    assert commands[-1] == "reconstructPar"


def test_kill_argv_has_no_shell_variable() -> None:
    wsl = kill_argv(_WSL, 42, platform="linux")
    assert wsl[:3] == ("wsl.exe", "-d", "Ubuntu-24.04")
    assert "kill -- -42" in wsl
    assert not any(part.startswith("$") for part in wsl)
    native = kill_argv(_NATIVE, 7, platform="linux")
    assert native == ("kill", "--", "-7")
    windows = kill_argv(_NATIVE, 7, platform="win32")
    assert windows == ("taskkill", "/PID", "7", "/T", "/F")
    with pytest.raises(ValueError, match="pid"):
        kill_argv(_NATIVE, 0, platform="win32")


def test_wsl_cancel_uses_linux_pgid_and_resume(tmp_path: Path) -> None:
    queue = JobQueue(bind(_WSL, _Probe()), tmp_path)
    queue.pid = 9999  # the wsl.exe pid on Windows
    assert queue.cancel() is None  # no pgid file yet: nothing safe to kill
    (tmp_path / ".foamstudio").mkdir()
    (tmp_path / ".foamstudio" / "job.pid").write_text("576\n", encoding="utf-8")
    argv = queue.cancel()
    assert argv is not None and argv[-1] == "kill -- -576"
    job = JobQueue(bind(_WSL, _Probe()), tmp_path).add_resume("simpleFoam")
    assert "startFrom -set latestTime && simpleFoam" in job.command


def test_windows_process_tree_kill() -> None:
    if sys.platform != "win32":
        pytest.skip("taskkill /T is the Windows kill path")
    code = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        text=True,
    )
    child_pid = 0
    try:
        assert parent.stdout is not None
        child_pid = int(parent.stdout.readline().strip())
        argv = kill_argv(_NATIVE, parent.pid, platform="win32")
        finished = subprocess.run(list(argv), capture_output=True, text=True, check=False)
        assert finished.returncode == 0
        parent.wait(timeout=15)
        listing = subprocess.run(
            ["tasklist", "/FI", f"PID eq {child_pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert "No tasks" in listing.stdout
    finally:
        if parent.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(parent.pid), "/T", "/F"],
                check=False,
            )
