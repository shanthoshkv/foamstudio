"""Exact commands the runtime wizard offers. Nothing here is executed by itself."""

from __future__ import annotations

from dataclasses import dataclass

_ESI_APT = (
    "curl -s https://dl.openfoam.com/add-debian-repo.sh | sudo bash"
    " && sudo apt-get update && sudo apt-get install -y openfoam2412-default"
)
_FOUNDATION_APT = (
    "sudo wget -qO /etc/apt/trusted.gpg.d/openfoam.asc https://dl.openfoam.org/gpg.key"
    " && sudo add-apt-repository -y http://dl.openfoam.org/ubuntu"
    " && sudo apt-get update && sudo apt-get install -y openfoam12"
)
_DOCKER = "docker pull opencfd/openfoam-run:2412"


@dataclass(frozen=True)
class InstallOffer:
    title: str
    command: str
    detail: str


def install_offers(platform: str) -> tuple[InstallOffer, ...]:
    docker = InstallOffer(
        "Docker image opencfd/openfoam-run:2412",
        _DOCKER,
        "Pulls the ESI 2412 runtime image. OpenFOAM stays outside FoamStudio.",
    )
    if platform == "win32":
        return (
            InstallOffer(
                "WSL2 Ubuntu 24.04",
                "wsl --install -d Ubuntu-24.04",
                "Windows may ask for a reboot. The window that opens is visible.",
            ),
            InstallOffer(
                "ESI OpenFOAM 2412 in Ubuntu-24.04",
                f'wsl.exe -d Ubuntu-24.04 -- bash -lc "{_ESI_APT}"',
                "Run after Ubuntu exists. sudo asks for the Linux password in that window.",
            ),
            InstallOffer(
                "Foundation OpenFOAM 12 in Ubuntu-24.04",
                f'wsl.exe -d Ubuntu-24.04 -- bash -lc "{_FOUNDATION_APT}"',
                "Foundation packages live under /opt/openfoam12.",
            ),
            docker,
        )
    if platform == "darwin":
        return (
            InstallOffer(
                "openfoam-app (gerlero) 2412",
                "brew install --cask openfoam2412",
                "Installs the native macOS app under /Applications.",
            ),
            docker,
        )
    return (
        InstallOffer(
            "ESI OpenFOAM 2412 from the apt repo",
            _ESI_APT,
            "Ubuntu or Debian. The package installs /usr/lib/openfoam/openfoam2412.",
        ),
        InstallOffer(
            "Foundation OpenFOAM 12 from the apt repo",
            _FOUNDATION_APT,
            "The package installs /opt/openfoam12.",
        ),
        docker,
    )


def visible_terminal(command: str, platform: str) -> tuple[str, ...]:
    if platform == "win32":
        return ("cmd.exe", "/c", "start", "FoamStudio", "cmd.exe", "/k", command)
    if platform == "darwin":
        escaped = command.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "Terminal" to do script "{escaped}"'
        return ("osascript", "-e", script)
    return ("x-terminal-emulator", "-e", "bash", "-lc", command)
