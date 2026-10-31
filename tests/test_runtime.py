"""Fake OpenFOAM runtimes: native, WSL, and Docker. No real install required."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from foamstudio.core.runtime import bind
from foamstudio.core.runtime.base import detect
from foamstudio.core.runtime.docker import parse_docker_image
from foamstudio.core.runtime.install_offers import install_offers, visible_terminal
from foamstudio.core.runtime.model import Installation, RuntimeFailure, suggestion_for
from foamstudio.core.runtime.native import classify_bashrc, detect_native
from foamstudio.core.runtime.paths import (
    bash_command,
    strip_zone_identifiers,
    windows_to_wsl,
    wsl_to_windows,
)
from foamstudio.core.runtime.probe import Completed, ProbeMissing, decode_output
from foamstudio.core.runtime.wsl import parse_wsl_names, wsl_steps

_ESI = Installation(
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
_DOCKER = Installation(
    kind="docker",
    flavour="esi",
    version="2412",
    bashrc="/usr/lib/openfoam/openfoam2412/etc/bashrc",
    image="opencfd/openfoam-run:2412",
)


class RecordProbe:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def run(self, argv, *, cwd=None, env=None, timeout=None):  # noqa: ANN001
        command = tuple(argv)
        self.calls.append((command, None if env is None else dict(env)))
        return Completed(command, self.returncode, self.stdout, self.stderr)


class MapProbe:
    def __init__(self, handler) -> None:  # noqa: ANN001
        self.handler = handler
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd=None, env=None, timeout=None):  # noqa: ANN001
        command = tuple(argv)
        self.calls.append(command)
        return self.handler(command)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/usr/lib/openfoam/openfoam2412/etc/bashrc", ("esi", "2412")),
        ("/opt/openfoam12/etc/bashrc", ("foundation", "12")),
        ("/home/me/OpenFOAM/OpenFOAM-v2412/etc/bashrc", ("esi", "2412")),
        ("/home/me/OpenFOAM/OpenFOAM-9/etc/bashrc", ("foundation", "9")),
        (
            "/Applications/OpenFOAM-v2412.app/Contents/Resources/etc/bashrc",
            ("esi", "2412"),
        ),
        (
            r"C:\Applications\OpenFOAM-12.app\Contents\Resources\etc\bashrc",
            ("foundation", "12"),
        ),
        ("/opt/openfoam2412/etc/bashrc", None),
        ("/usr/bin/bashrc", None),
    ],
)
def test_classify_bashrc(path: str, expected: tuple[str, str] | None) -> None:
    assert classify_bashrc(path) == expected


def test_detect_native_tree(tmp_path: Path) -> None:
    etc = tmp_path / "OpenFOAM-v2412.app" / "Contents" / "Resources" / "etc"
    etc.mkdir(parents=True)
    (etc / "bashrc").write_text("# bashrc\n", encoding="utf-8")
    skipped = tmp_path / "notfoam" / "etc"
    skipped.mkdir(parents=True)
    (skipped / "bashrc").write_text("# no\n", encoding="utf-8")
    found = detect_native((tmp_path,))
    assert len(found) == 1
    assert found[0].kind == "native"
    assert found[0].flavour == "esi"
    assert found[0].version == "2412"
    assert found[0].bashrc.endswith("/OpenFOAM-v2412.app/Contents/Resources/etc/bashrc")


def test_path_translation_round_trip() -> None:
    assert windows_to_wsl(r"C:\Users\me\my case") == "/mnt/c/Users/me/my case"
    assert windows_to_wsl("C:/") == "/mnt/c"
    assert wsl_to_windows("/mnt/c/Users/me/my case") == "C:/Users/me/my case"
    assert wsl_to_windows(windows_to_wsl("d:/work/case")) == "D:/work/case"
    with pytest.raises(ValueError, match="Windows path"):
        windows_to_wsl("/mnt/c/work")
    with pytest.raises(ValueError, match="WSL drive"):
        wsl_to_windows("C:/work")


def test_bash_command_shape() -> None:
    body = bash_command(
        "/usr/lib/openfoam/openfoam2412/etc/bashrc",
        "/mnt/c/case",
        "simpleFoam -help",
        {"FOAM_SIGFPE": "1"},
    )
    assert body == (
        "export FOAM_SIGFPE='1'"
        " && source '/usr/lib/openfoam/openfoam2412/etc/bashrc'"
        " && cd '/mnt/c/case'"
        " && simpleFoam -help"
    )
    with pytest.raises(ValueError, match="empty"):
        bash_command("/b", "/c", "  ")
    with pytest.raises(ValueError, match="FOAM-CASE"):
        bash_command("/b", "/c", "icoFoam", {"FOAM-CASE": "1"})


def test_wsl_steps_have_no_dollar() -> None:
    chmod, bash = wsl_steps("Ubuntu-24.04", "/mnt/c/cases/check/.foamstudio/run.sh")
    assert chmod[:6] == ("wsl.exe", "-d", "Ubuntu-24.04", "--", "chmod", "+x")
    assert bash[:7] == ("wsl.exe", "-d", "Ubuntu-24.04", "--", "setsid", "-w", "bash")
    joined = " ".join(chmod + bash)
    assert "$" not in joined
    with pytest.raises(ValueError, match=r"\$"):
        wsl_steps("Ubuntu-24.04", "/mnt/c/cases/$work/run.sh")


def test_wsl_names_and_utf16() -> None:
    text = "\ufeffWindows Subsystem for Linux Distributions:\nUbuntu-24.04 (Default)\n"
    assert parse_wsl_names(text) == ("Ubuntu-24.04",)
    decoded = decode_output("Ubuntu-24.04\n".encode("utf-16"))
    assert "Ubuntu-24.04" in decoded


def test_parse_docker_image() -> None:
    image = parse_docker_image("opencfd/openfoam-run:2412")
    assert image is not None
    assert image.flavour == "esi"
    assert image.bashrc == "/usr/lib/openfoam/openfoam2412/etc/bashrc"
    foundation = parse_docker_image("openfoam/openfoam12:12")
    assert foundation is not None
    assert foundation.flavour == "foundation"
    assert foundation.bashrc == "/opt/openfoam12/etc/bashrc"
    assert parse_docker_image("opencfd/openfoam-run:latest") is None
    assert parse_docker_image("opencfd/openfoam-run:<none>") is None


def test_native_run_sources_bashrc(tmp_path: Path) -> None:
    case = tmp_path / "cavity"
    case.mkdir()
    marker = case / "blockMeshDict:Zone.Identifier"
    try:
        marker.write_text("zone", encoding="utf-8")
    except OSError:
        marker = None
    probe = RecordProbe(stdout="Usage: simpleFoam\n")
    result = asyncio.run(bind(_ESI, probe).run("simpleFoam -help", case))
    assert result.returncode == 0
    argv, env = probe.calls[0]
    assert argv[0:2] == ("bash", "-lc")
    assert "source '/usr/lib/openfoam/openfoam2412/etc/bashrc'" in argv[2]
    assert "simpleFoam -help" in argv[2]
    assert env is not None
    assert env["MSYS_NO_PATHCONV"] == "1"
    assert env["MSYS2_ARG_CONV_EXCL"] == "*"
    if marker is not None:
        assert not marker.exists()


def test_docker_argv_mounts_the_case(tmp_path: Path) -> None:
    probe = RecordProbe(stdout="Usage\n")
    asyncio.run(bind(_DOCKER, probe).run("simpleFoam -help", tmp_path))
    argv = probe.calls[0][0]
    assert argv[:4] == ("docker", "run", "--rm", "-v")
    assert argv[4].endswith(":/case")
    assert "$" not in argv[4]
    assert argv[5:8] == ("-w", "/case", "opencfd/openfoam-run:2412")
    assert argv[8:10] == ("bash", "-lc")
    assert "simpleFoam -help" in argv[10]


def test_docker_rejects_dollar_in_the_mount() -> None:
    with pytest.raises(ValueError, match=r"\$"):
        bind(_DOCKER, RecordProbe()).plan("simpleFoam -help", Path("C:/cases/$work"))


def test_wsl_run_writes_an_lf_script(tmp_path: Path) -> None:
    if re.match(r"^[A-Za-z]:[\\/]", str(tmp_path)) is None:
        pytest.skip("WSL run() is exercised on a Windows case path")
    case = tmp_path / "cavity"
    case.mkdir()
    probe = RecordProbe(stdout="Usage: simpleFoam\n")
    asyncio.run(bind(_WSL, probe).run("simpleFoam -help", case))
    script = next((case / ".foamstudio").glob("run-*.sh"))
    data = script.read_bytes()
    assert data.startswith(b"#!/bin/bash\n")
    assert data.count(b"#!/bin/bash") == 1
    assert b"\r" not in data
    assert b"source '/usr/lib/openfoam/openfoam2412/etc/bashrc'" in data
    assert b"simpleFoam -help" in data
    mounted = windows_to_wsl(str(script))
    chmod, bash = (probe.calls[0][0], probe.calls[1][0])
    assert chmod[:6] == ("wsl.exe", "-d", "Ubuntu-24.04", "--", "chmod", "+x")
    assert chmod[6] == mounted
    assert bash[:7] == ("wsl.exe", "-d", "Ubuntu-24.04", "--", "setsid", "-w", "bash")
    assert bash[7] == mounted
    assert "$" not in " ".join(chmod + bash)
    assert "/tmp/" not in mounted


def test_failed_command_reports_the_fix(tmp_path: Path) -> None:
    probe = RecordProbe(127, stderr="simpleFoam: command not found\n")
    with pytest.raises(RuntimeFailure) as caught:
        asyncio.run(bind(_ESI, probe).run("simpleFoam -help", tmp_path))
    err = caught.value
    assert err.returncode == 127
    assert "simpleFoam -help" in err.command
    assert "OpenFOAM did not provide this command" in err.suggestion
    assert "command not found" in err.log_tail


def test_timeout_is_a_runtime_failure(tmp_path: Path) -> None:
    class Slow:
        def run(self, argv, *, cwd=None, env=None, timeout=None):  # noqa: ANN001
            raise TimeoutError(f"bash exceeded {timeout}s.")

    with pytest.raises(RuntimeFailure) as caught:
        asyncio.run(bind(_ESI, Slow()).run("simpleFoam -help", tmp_path, timeout=1))
    assert caught.value.returncode == 124
    assert "exceeded" in str(caught.value)


def test_missing_case_is_a_runtime_failure(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(RuntimeFailure, match="Create the case directory"):
        asyncio.run(bind(_ESI, RecordProbe()).run("simpleFoam -help", missing))


def test_detect_fake_wsl_and_docker(tmp_path: Path) -> None:
    packaged = tmp_path / "openfoam" / "openfoam2412" / "etc"
    packaged.mkdir(parents=True)
    (packaged / "bashrc").write_text("#\n", encoding="utf-8")

    def handler(command: tuple[str, ...]) -> Completed:
        if command[:3] == ("wsl.exe", "-l", "-q"):
            return Completed(command, 0, "Ubuntu-24.04\n", "")
        if command[:3] == ("wsl.exe", "-d", "Ubuntu-24.04"):
            stdout = "/usr/lib/openfoam/openfoam2412/etc/bashrc\n/opt/openfoam12/etc/bashrc\n"
            return Completed(command, 0, stdout, "")
        if command[0] == "docker":
            stdout = (
                "opencfd/openfoam-run:2412\nopencfd/openfoam-run:latest\nopenfoam/openfoam12:12\n"
            )
            return Completed(command, 0, stdout, "")
        raise AssertionError(command)

    probe = MapProbe(handler)
    report = detect(probe, platform="win32", native_roots=(tmp_path,))
    native = [item for item in report.installations if item.kind == "native"]
    assert len(native) == 1
    assert native[0].version == "2412"
    wsl = {
        (item.flavour, item.version, item.distro)
        for item in report.installations
        if item.kind == "wsl"
    }
    assert wsl == {("esi", "2412", "Ubuntu-24.04"), ("foundation", "12", "Ubuntu-24.04")}
    images = [item.image for item in report.installations if item.kind == "docker"]
    assert images == ["opencfd/openfoam-run:2412", "openfoam/openfoam12:12"]
    for call in probe.calls:
        if call[0] == "wsl.exe":
            assert all("$" not in part for part in call)


def test_missing_wsl_and_docker_are_notes() -> None:
    class Missing:
        def run(self, argv, *, cwd=None, env=None, timeout=None):  # noqa: ANN001
            raise ProbeMissing(tuple(argv)[0])

    report = detect(Missing(), platform="win32", native_roots=())
    text = "\n".join(report.notes)
    assert report.installations == ()
    assert "wsl.exe was not found on PATH." in text
    assert "wsl --install -d Ubuntu-24.04" in text
    assert "docker was not found on PATH." in text
    assert "Docker is optional." in text


def test_docker_daemon_down_is_a_note() -> None:
    class Down:
        def run(self, argv, *, cwd=None, env=None, timeout=None):  # noqa: ANN001
            command = tuple(argv)
            if command[0] == "docker":
                return Completed(command, 1, "", "Cannot connect to the Docker daemon\n")
            raise ProbeMissing(command[0])

    report = detect(Down(), platform="linux", native_roots=())
    text = "\n".join(report.notes)
    assert "docker" in text
    assert "Start Docker, or use a native or WSL install." in text


def test_install_offer_commands() -> None:
    windows = [offer.command for offer in install_offers("win32")]
    assert "wsl --install -d Ubuntu-24.04" in windows
    assert any(
        command.startswith("wsl.exe -d Ubuntu-24.04") and "openfoam2412-default" in command
        for command in windows
    )
    assert any(
        "openfoam12" in command and command.startswith("wsl.exe -d Ubuntu-24.04")
        for command in windows
    )
    assert "docker pull opencfd/openfoam-run:2412" in windows

    linux = [offer.command for offer in install_offers("linux")]
    assert linux[0].startswith("curl -s https://dl.openfoam.com/add-debian-repo.sh")
    assert "openfoam2412-default" in linux[0]
    assert "https://dl.openfoam.org/gpg.key" in linux[1]
    assert "openfoam12" in linux[1]
    assert linux[2] == "docker pull opencfd/openfoam-run:2412"

    macos = [offer.command for offer in install_offers("darwin")]
    assert macos == [
        "brew install --cask openfoam2412",
        "docker pull opencfd/openfoam-run:2412",
    ]


def test_visible_terminal_commands() -> None:
    windows = visible_terminal("wsl --install -d Ubuntu-24.04", "win32")
    assert windows[:6] == ("cmd.exe", "/c", "start", "FoamStudio", "cmd.exe", "/k")
    assert windows[6] == "wsl --install -d Ubuntu-24.04"
    linux = visible_terminal("echo hi", "linux")
    assert linux == ("x-terminal-emulator", "-e", "bash", "-lc", "echo hi")
    macos = visible_terminal('echo "hi"', "darwin")
    assert macos[0] == "osascript"
    assert "do script" in macos[2]


def test_suggestions() -> None:
    assert "OpenFOAM did not provide this command" in suggestion_for(
        kind="native", stderr="simpleFoam: command not found", returncode=127
    )
    assert "wsl --install -d Ubuntu-24.04" in suggestion_for(
        kind="wsl", stderr="Error: 0x80070003", returncode=1
    )
    assert "Start Docker" in suggestion_for(
        kind="docker", stderr="Cannot connect to the Docker daemon", returncode=1
    )


def test_zone_identifier_removal(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    marker = case / "blockMeshDict:Zone.Identifier"
    try:
        marker.write_text("zone", encoding="utf-8")
    except OSError:
        pytest.skip("filesystem rejects colon in file names")
    assert strip_zone_identifiers(case) == [marker]
    assert not marker.exists()


def test_installation_round_trip_rejects_ssh() -> None:
    assert "image" not in _WSL.to_dict()
    assert Installation.from_dict(_WSL.to_dict()) == _WSL
    assert Installation.from_dict(_DOCKER.to_dict()) == _DOCKER
    raw = _WSL.to_dict()
    raw["kind"] = "ssh"
    with pytest.raises(ValueError, match="ssh"):
        Installation.from_dict(raw)
