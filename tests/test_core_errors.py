"""Error branches users actually hit: bad case.json, bad project folders, path traversal,
and a real (non-OpenFOAM) live job through the job queue."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from foamstudio.core.jobs import JobQueue
from foamstudio.core.project import ProjectError, create_project, open_project, write_case_files
from foamstudio.core.runtime import bind
from foamstudio.core.runtime.model import Installation
from foamstudio.core.runtime.probe import SubprocessProbe, decode_output
from foamstudio.core.spec import SpecError, load_spec

_GOOD = {
    "schema": 1,
    "generator": "2.2.1",
    "caseName": "c",
    "openfoamVersion": 2412,
    "state": {"solver": "simpleFoam", "patches": [{"name": "inlet", "role": "inlet"}]},
}


def _spec(**changes: object) -> str:
    data = json.loads(json.dumps(_GOOD))
    for key, value in changes.items():
        if key.startswith("state."):
            data["state"][key[6:]] = value
        else:
            data[key] = value
    return json.dumps(data)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "JSON"),
        ("[1]", "object"),
        (_spec(schema=2), "schema"),
        (_spec(generator=""), "generator"),
        (_spec(caseName="a/b"), "caseName"),
        (_spec(openfoamVersion=True), "openfoamVersion"),
        (_spec(state=[]), "state"),
        (_spec(**{"state.solver": ""}), "solver"),
        (_spec(**{"state.patches": {}}), "patches"),
        (_spec(**{"state.patches": [1]}), "patches[0]"),
        (_spec(**{"state.patches": [{"name": "x"}]}), "name and role"),
    ],
)
def test_bad_case_json_is_explained(text: str, message: str) -> None:
    with pytest.raises(SpecError) as caught:
        load_spec(text)
    assert message.lower() in (caught.value.message + caught.value.suggestion).lower()
    assert caught.value.suggestion


def test_good_case_json_loads() -> None:
    assert load_spec(_spec())["caseName"] == "c"


def test_project_folder_errors(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match="version"):
        create_project(tmp_path / "p", app_version="")
    project = create_project(tmp_path / "p", app_version="0.9.0")
    with pytest.raises(ProjectError, match="already"):
        create_project(tmp_path / "p", app_version="0.9.0")
    with pytest.raises(ProjectError, match="does not exist"):
        open_project(tmp_path / "missing")
    afile = tmp_path / "file.txt"
    afile.write_text("x", encoding="utf-8")
    with pytest.raises(ProjectError, match="not a folder"):
        open_project(afile)
    with pytest.raises(ProjectError, match="foamstudio.json"):
        open_project(project.case_dir)
    (project.root / "foamstudio.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ProjectError):
        open_project(project.root)


@pytest.mark.parametrize("key", ["../evil", "/etc/passwd", "C:/x", "c/../../x", "c/"])
def test_case_writes_cannot_escape_the_case_folder(tmp_path: Path, key: str) -> None:
    project = create_project(tmp_path / "p", app_version="0.9.0")
    with pytest.raises(ProjectError):
        write_case_files(
            project,
            {key: "x"},
            case_name="c",
            command="node gen",
            app_version="0.9.0",
            generator_version="2.2.1",
        )


def test_case_write_needs_files_and_command(tmp_path: Path) -> None:
    project = create_project(tmp_path / "p", app_version="0.9.0")
    common = {"case_name": "c", "app_version": "0.9.0", "generator_version": "2.2.1"}
    with pytest.raises(ProjectError, match="no files"):
        write_case_files(project, {}, command="node gen", **common)
    with pytest.raises(ProjectError, match="command"):
        write_case_files(project, {"c/system/controlDict": "x"}, command=" ", **common)
    written = write_case_files(project, {"c/system/controlDict": "x"}, command="node", **common)
    assert written[0].read_text(encoding="utf-8") == "x"


def test_decode_output_survives_bad_bytes() -> None:
    assert decode_output(b"ok") == "ok"
    assert isinstance(decode_output(b"\xff\xfe\x00bad"), str)


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="native runtimes are Linux/macOS; on Windows `bash` resolves to WSL's bash.exe",
)
def test_live_job_runs_and_reports_failure(tmp_path: Path) -> None:
    """The real subprocess path (`live=True`) with a native runtime and an empty bashrc."""
    bashrc = tmp_path / "bashrc"
    bashrc.write_text("", encoding="utf-8")
    native = Installation(kind="native", flavour="esi", version="2412", bashrc=str(bashrc))
    case = tmp_path / "case"
    case.mkdir()
    queue = JobQueue(bind(native, SubprocessProbe()), case)
    queue.add("echo hello > out.txt", name="echo")
    queue.add("exit 3", name="fail")
    queue.add("echo never", name="after")
    jobs = queue.run_blocking(live=True)
    assert [job.status for job in jobs] == ["succeeded", "failed", "cancelled"]
    assert jobs[1].returncode == 3
    assert (case / "out.txt").read_text().strip() == "hello"


class _Scripted:
    """Probe that answers each argv from a function; raises if it returns an exception."""

    def __init__(self, answer) -> None:  # noqa: ANN001
        self.answer = answer

    def run(self, argv, *, cwd=None, env=None, timeout=None):  # noqa: ANN001
        from foamstudio.core.runtime.probe import Completed

        result = self.answer(tuple(argv))
        if isinstance(result, BaseException):
            raise result
        code, out = result
        return Completed(tuple(argv), code, out, "")


def test_wsl_detection_reports_every_failure_mode() -> None:
    from foamstudio.core.runtime.probe import ProbeMissing
    from foamstudio.core.runtime.wsl import detect_wsl

    found, notes = detect_wsl(_Scripted(lambda a: ProbeMissing("wsl.exe")))
    assert found == () and "wsl --install" in notes[0]
    found, notes = detect_wsl(_Scripted(lambda a: TimeoutError("slow")))
    assert found == () and "wsl --shutdown" in notes[0]
    found, notes = detect_wsl(_Scripted(lambda a: (1, "")))
    assert found == () and "Command failed (1)" in notes[0]

    def distro(argv: tuple[str, ...]) -> object:
        if argv[1] == "-l":
            return (0, "Ubuntu-24.04\nBroken\nSlow\n")
        name = argv[2]
        if name == "Broken":
            return (2, "")
        if name == "Slow":
            return TimeoutError("listing")
        return (0, "/usr/lib/openfoam/openfoam2412/etc/bashrc\n\n/opt/unknown/thing\n")

    found, notes = detect_wsl(_Scripted(distro))
    assert [(i.flavour, i.version, i.distro) for i in found] == [("esi", "2412", "Ubuntu-24.04")]
    assert any("Broken" in note for note in notes) and any("timed out" in note for note in notes)


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ("nope", "object"),
        ({"kind": "moon"}, "kind"),
        ({"kind": "wsl", "flavour": "x"}, "flavour"),
        ({"kind": "wsl", "flavour": "esi", "version": "2412", "bashrc": "/b"}, "distro"),
        ({"kind": "docker", "flavour": "esi", "version": "2412", "bashrc": "/b"}, "image"),
        ({"kind": "ssh", "flavour": "esi", "version": "2412", "bashrc": "/b"}, "host"),
        (
            {"kind": "ssh", "flavour": "esi", "version": "2412", "bashrc": "/b", "host": "h"},
            "user",
        ),
        ({"kind": "native", "flavour": "esi", "version": 2412, "bashrc": "/b"}, "string"),
        ({"kind": "native", "flavour": "esi", "version": " ", "bashrc": "/b"}, "version"),
    ],
)
def test_runtime_records_are_validated(record: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Installation.from_dict(record)


def test_crash_upload_needs_opt_in_url_and_file(tmp_path: Path) -> None:
    from foamstudio.core.telemetry import TelemetryError, maybe_upload

    report = tmp_path / "crash.txt"
    assert maybe_upload(report, enabled=False, endpoint="https://x") is None
    with pytest.raises(TelemetryError, match="no upload URL"):
        maybe_upload(report, enabled=True, endpoint=None)
    with pytest.raises(TelemetryError, match="does not exist"):
        maybe_upload(report, enabled=True, endpoint="https://x")
    report.write_text("trace", encoding="utf-8")
    plan = maybe_upload(report, enabled=True, endpoint="https://x")
    assert plan is not None and plan.body() == b"trace"


def test_path_helpers_guard_shell_inputs(tmp_path: Path) -> None:
    from foamstudio.core.runtime.paths import (
        bash_command,
        launch_env,
        reject_dollar,
        sh_quote,
        windows_to_wsl,
        write_runner,
        wsl_to_windows,
    )

    assert windows_to_wsl("D:\\") == "/mnt/d"
    assert wsl_to_windows("/mnt/d") == "D:/"
    with pytest.raises(ValueError):
        windows_to_wsl("/already/posix")
    with pytest.raises(ValueError):
        wsl_to_windows("/home/me")
    assert sh_quote("it's") == "'it'" + "\\'" + "'s'"
    with pytest.raises(ValueError, match="empty"):
        bash_command("/b", "/c", "   ")
    with pytest.raises(ValueError, match="exported"):
        bash_command("/b", "/c", "run", {"BAD-NAME": "1"})
    assert "export OMP_NUM_THREADS='2'" in bash_command("/b", "/c", "run", {"OMP_NUM_THREADS": "2"})
    env = launch_env({"X": "1"})
    assert env["X"] == "1" and env["MSYS_NO_PATHCONV"] == "1"
    with pytest.raises(ValueError, match=r"\$"):
        reject_dollar("a$b", what="The path")
    with pytest.raises(ValueError, match="LF"):
        write_runner(tmp_path, "echo hi\r\n")
    runner = write_runner(tmp_path, "echo hi")
    assert runner.read_bytes().startswith(b"#!/bin/bash\n")


def test_subprocess_probe_runs_times_out_and_reports_missing(tmp_path: Path) -> None:
    from foamstudio.core.runtime.probe import ProbeMissing

    probe = SubprocessProbe()
    done = probe.run([sys.executable, "-c", "print('ok')"], cwd=tmp_path, timeout=30)
    assert done.returncode == 0 and done.stdout.strip() == "ok"
    with pytest.raises(TimeoutError, match="exceeded"):
        probe.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.5)
    with pytest.raises(ProbeMissing):
        probe.run(["foamstudio-no-such-program-xyz"])
