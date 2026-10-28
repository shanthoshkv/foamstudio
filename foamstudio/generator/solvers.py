"""The 25 solvers exercised by tests/gen_fn.js.

MRF and AMI rows in that table are extra cases of simpleFoam and pimpleFoam.
They are not extra solvers. The list is the acceptance set for Phase 2.
"""

from __future__ import annotations

SOLVERS: tuple[str, ...] = (
    "simpleFoam",
    "pimpleFoam",
    "pisoFoam",
    "icoFoam",
    "porousSimpleFoam",
    "SRFSimpleFoam",
    "SRFPimpleFoam",
    "potentialFoam",
    "scalarTransportFoam",
    "rhoSimpleFoam",
    "rhoPimpleFoam",
    "sonicFoam",
    "rhoCentralFoam",
    "buoyantSimpleFoam",
    "buoyantPimpleFoam",
    "reactingFoam",
    "rhoReactingFoam",
    "XiFoam",
    "chtMultiRegionSimpleFoam",
    "chtMultiRegionFoam",
    "interFoam",
    "compressibleInterFoam",
    "interPhaseChangeFoam",
    "solidDisplacementFoam",
    "overPimpleDyMFoam",
)

TAGGED_CASES: tuple[str, ...] = ("2412_simpleFoam_MRF", "2412_pimpleFoam_AMI")
ACCEPTANCE_VERSION = "2412"


def golden_key(solver: str, version: str = ACCEPTANCE_VERSION) -> str:
    return f"{version}_{solver}"
