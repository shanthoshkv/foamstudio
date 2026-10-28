"""OpenFOAM runtimes. OpenFOAM is always an external process."""

from foamstudio.core.runtime.base import BoundRuntime, RunPlan, bind, detect
from foamstudio.core.runtime.model import (
    CommandResult,
    DetectionReport,
    Installation,
    RuntimeFailure,
)

__all__ = [
    "BoundRuntime",
    "CommandResult",
    "DetectionReport",
    "Installation",
    "RunPlan",
    "RuntimeFailure",
    "bind",
    "detect",
]
