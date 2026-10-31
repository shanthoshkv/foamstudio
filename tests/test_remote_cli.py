"""SSH transport, update feed, crash upload plan, and batch CLI actions."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from foamstudio.app.main import main
from foamstudio.core.jobs import kill_argv
from foamstudio.core.runtime import bind
from foamstudio.core.runtime.model import Installation, RuntimeFailure
from foamstudio.core.runtime.ssh import pbs_script, pull_argv, push_argv, slurm_script, trame_script
from foamstudio.core.telemetry import TelemetryError, maybe_upload
from foamstudio.core.update import parse_atom, sha256_matches, update_allowed

_SSH = Installation(
    kind="ssh",
    flavour="foundation",
    version="12",
    bashrc="/opt/openfoam12/etc/bashrc",
    host="hpc.example",
    user="me",
    remote_case="/work/case",
    scheduler="slurm",
)
_WSL = Installation(
    kind="wsl",
    flavour="esi",
    version="2412",
    bashrc="/usr/lib/openfoam/openfoam2412/etc/bashrc",
    distro="Ubuntu-24.04",
)


def test_ssh_plan_batchmode_and_round_trip(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    plan = bind(_SSH).plan("simpleFoam", case)
    argv = plan.steps[0]
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert "me@hpc.example" in argv
    # sshd re-splits the joined remote argv: the whole script must survive as one bash -lc arg
    remote = shlex.split(" ".join(argv[argv.index("me@hpc.example") + 1 :]))
    assert remote[:2] == ["bash", "-lc"] and len(remote) == 3
    assert remote[2] == plan.body
    kill = shlex.split(kill_argv(_SSH, 42, platform="linux")[-1])
    assert kill == ["bash", "-lc", "kill -- -42"]
    assert "$" not in _SSH.host
    assert Installation.from_dict(_SSH.to_dict()) == _SSH
    wsl = _WSL.to_dict()
    assert "host" not in wsl
    wsl["kind"] = "ssh"
    with pytest.raises(ValueError, match="ssh"):
        Installation.from_dict(wsl)
    bad = Installation(
        kind="ssh",
        flavour="foundation",
        version="12",
        bashrc="/opt/openfoam12/etc/bashrc",
        host="hpc$HOME",
        user="me",
    )
    with pytest.raises(RuntimeFailure, match="\\$"):
        bind(bad).plan("simpleFoam", case)


def test_scheduler_scripts_and_sync() -> None:
    slurm = slurm_script(_SSH, "simpleFoam -parallel", ntasks=8)
    assert "#SBATCH --ntasks=8" in slurm
    assert "source /opt/openfoam12/etc/bashrc" in slurm
    pbs = pbs_script(_SSH, "simpleFoam -parallel", ncpus=4)
    assert "#PBS -N foamstudio" in pbs
    assert push_argv(_SSH, "C:/case", "/work/case")[0] == "scp"
    assert "BatchMode=yes" in pull_argv(_SSH, "/work/case", "C:/case")
    script = trame_script("/work/case/case.foam")
    assert "trame is not installed" in script
    with pytest.raises(ValueError, match="\\$"):
        trame_script("/work/$case/case.foam")


def test_update_feed_and_telemetry(tmp_path: Path) -> None:
    digest = "ab" * 32
    feed = f"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>0.9.0</title>
    <link href="https://example.invalid/foamstudio-0.9.0.zip"/>
    <summary>sha256:{digest} rollout:10</summary>
  </entry>
</feed>
"""
    release = parse_atom(feed)[0]
    assert release.version == "0.9.0"
    assert release.rollout == 10
    assert sha256_matches(b"payload", digest) is False
    assert sha256_matches(b"payload", "") is False
    assert update_allowed(configured=False, rollout=100, bucket=0) is False
    assert update_allowed(configured=True, rollout=10, bucket=3) is True
    assert update_allowed(configured=True, rollout=10, bucket=10) is False
    report = tmp_path / "crash.txt"
    report.write_text("trace", encoding="utf-8")
    assert maybe_upload(report, enabled=False, endpoint="https://example.invalid") is None
    with pytest.raises(TelemetryError, match="upload URL"):
        maybe_upload(report, enabled=True, endpoint=None)


def test_cli_batch_actions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "proj"
    assert main(["--project", str(project)]) == 2
    captured = capsys.readouterr()
    assert "write-case" in captured.err
    stl = tmp_path / "inlet.stl"
    stl.write_text(
        "solid inlet\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid inlet\n",
        encoding="utf-8",
    )
    code = main(["--project", str(project), "--import-geometry", str(stl), "--block-mesh", "box"])
    assert code == 0
    assert (project / "geometry" / "inlet.stl").is_file()
    patches = json.loads((project / "geometry" / "patches.json").read_text(encoding="utf-8"))
    assert patches[0]["name"] == "inlet"
    mesh = (project / "case" / "system" / "blockMeshDict").read_text(encoding="utf-8")
    assert "blockMeshDict" in mesh
    report = tmp_path / "report.html"
    assert main(["--project", str(project), "--report", str(report)]) == 0
    err = capsys.readouterr().err
    assert "No solver log" in err
    assert "Setup" in report.read_text(encoding="utf-8")
    assert main(["--project", str(project), "--run-case"]) == 2
    assert "runtime" in capsys.readouterr().err
    assert main(["--self-test"]) == 0
    assert "foamstudio: launched" in capsys.readouterr().out
