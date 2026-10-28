"""Crash-report upload. Off unless the user opts in. The local file is always written."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class TelemetryError(Exception):
    def __init__(self, message: str, suggestion: str) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"{message}\n\n{suggestion}")


@dataclass(frozen=True)
class UploadPlan:
    endpoint: str
    report: Path

    def body(self) -> bytes:
        return self.report.read_bytes()


def post_report(plan: UploadPlan) -> int:
    """POST the crash file. Callers must already have checked the opt-in flags."""
    import urllib.request

    request = urllib.request.Request(
        plan.endpoint,
        data=plan.body(),
        method="POST",
        headers={"Content-Type": "text/plain"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return int(response.status)


def maybe_upload(report: Path, *, enabled: bool, endpoint: str | None) -> UploadPlan | None:
    """Return a plan, or None when crash reports are off. This function does not open a socket."""
    if not enabled:
        return None
    if not endpoint:
        raise TelemetryError(
            "Crash reports are enabled, but no upload URL is configured.",
            suggestion=(
                "Set FOAMSTUDIO_CRASH_URL, or turn crash reports off. "
                "The local crash file is still written either way."
            ),
        )
    if not report.is_file():
        raise TelemetryError(
            f"Crash report {report} does not exist.",
            suggestion="Write the local crash file before uploading it.",
        )
    return UploadPlan(endpoint, report)
