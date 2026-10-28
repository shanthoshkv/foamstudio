"""OpenFOAM container images. The image is not bundled."""

from __future__ import annotations

import re

from foamstudio.core.runtime.model import Installation, format_argv, log_tail
from foamstudio.core.runtime.probe import Completed, Probe, ProbeMissing

_IMAGES = ("docker", "images", "--format", "{{.Repository}}:{{.Tag}}")
_ESI_REPOS = frozenset({"opencfd/openfoam-run", "opencfd/openfoam-default", "opencfd/openfoam-dev"})
_VERSION = re.compile(r"v?(\d{4})")
_FOUNDATION_REPO = re.compile(r"openfoam/openfoam(\d{1,2})$")


def parse_docker_image(line: str) -> Installation | None:
    text = line.strip()
    if ":" not in text:
        return None
    repo, tag = text.rsplit(":", 1)
    if tag in {"", "<none>", "latest"}:
        return None
    esi = _VERSION.fullmatch(tag)
    if repo in _ESI_REPOS and esi is not None:
        version = esi.group(1)
        return Installation(
            kind="docker",
            flavour="esi",
            version=version,
            bashrc=f"/usr/lib/openfoam/openfoam{version}/etc/bashrc",
            image=f"{repo}:{tag}",
        )
    foundation = _FOUNDATION_REPO.fullmatch(repo)
    if foundation is not None and tag == foundation.group(1):
        version = foundation.group(1)
        return Installation(
            kind="docker",
            flavour="foundation",
            version=version,
            bashrc=f"/opt/openfoam{version}/etc/bashrc",
            image=f"{repo}:{tag}",
        )
    return None


def detect_docker(
    probe: Probe, *, timeout: float = 15
) -> tuple[tuple[Installation, ...], tuple[str, ...]]:
    try:
        completed = probe.run(_IMAGES, timeout=timeout)
    except ProbeMissing as exc:
        return (), (f"{exc} Docker is optional.",)
    except TimeoutError as exc:
        return (), (f"docker images timed out.\n{exc}\nStart Docker and detect again.",)
    if completed.returncode != 0:
        return (), (_failed(completed, "Start Docker, or use a native or WSL install."),)
    found: list[Installation] = []
    seen: set[str] = set()
    for line in completed.stdout.splitlines():
        installation = parse_docker_image(line)
        if installation is None or installation.image in seen:
            continue
        seen.add(installation.image)
        found.append(installation)
    return tuple(found), ()


def _failed(completed: Completed, suggestion: str) -> str:
    return (
        f"Command failed ({completed.returncode}).\n{format_argv(completed.argv)}\n\n"
        f"{log_tail(completed.stdout, completed.stderr)}\n\n{suggestion}"
    )
