"""GitHub Releases atom feed. Updates stay off until a channel is configured."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str
    rollout: int


def parse_atom(text: str) -> tuple[Release, ...]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(
            f"The update feed is not Atom XML: {exc}\n\n"
            "Point FoamStudio at a GitHub Releases atom feed."
        ) from exc
    releases: list[Release] = []
    for entry in root.findall(f"{_ATOM}entry"):
        title = _text(entry, "title")
        link = entry.find(f"{_ATOM}link")
        url = "" if link is None else link.attrib.get("href", "")
        summary = _text(entry, "summary")
        digest, rollout = _summary_fields(summary)
        if title and url:
            releases.append(Release(title, url, digest, rollout))
    return tuple(releases)


def _text(entry: ET.Element, name: str) -> str:
    node = entry.find(f"{_ATOM}{name}")
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _summary_fields(summary: str) -> tuple[str, int]:
    digest = ""
    rollout = 100
    for part in summary.split():
        if part.startswith("sha256:"):
            digest = part.split(":", 1)[1]
        if part.startswith("rollout:"):
            rollout = int(part.split(":", 1)[1])
    return digest, rollout


def sha256_matches(payload: bytes, expected: str) -> bool:
    if not expected:
        return False
    return hashlib.sha256(payload).hexdigest() == expected.lower()


def update_allowed(*, configured: bool, rollout: int, bucket: int) -> bool:
    """Staged rollout. `configured` is false until the user sets an update URL."""
    if not configured:
        return False
    if rollout <= 0:
        return False
    if rollout >= 100:
        return True
    return 0 <= bucket < rollout
