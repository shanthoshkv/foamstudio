"""Structural case.json checks. Schema 1 matches the generator's SPEC_SCHEMA.

Semantic checks stay in ``validateSpec`` inside ``openfoam_case_generator.html``.
This module does not write OpenFOAM dictionaries.
"""

from __future__ import annotations

import json
from typing import Any, cast

SPEC_SCHEMA = 1
GENERATOR_VERSION = "2.2.1"


class SpecError(Exception):
    """case.json cannot be handed to the generator. The message includes a fix."""

    def __init__(self, message: str, *, suggestion: str) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(f"{message}\n\n{suggestion}")


def load_spec(text: str) -> dict[str, Any]:
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SpecError(
            f"case.json is not valid JSON: {exc}",
            suggestion="Choose a case.json produced by the OpenFOAM Case Generator.",
        ) from exc
    return parse_spec(data)


def parse_spec(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SpecError(
            "case.json is not a JSON object.",
            suggestion="Choose a case.json produced by the OpenFOAM Case Generator.",
        )
    spec = cast(dict[str, Any], data)
    migrated = migrate_spec(spec)
    _require_structure(migrated)
    return migrated


def migrate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a schema-1 spec. Later schemas get a converter here, not a second writer."""

    schema = spec.get("schema")
    if not isinstance(schema, bool) and schema == SPEC_SCHEMA:
        return spec
    raise SpecError(
        f"case.json schema {schema!r} is not supported. This build reads schema {SPEC_SCHEMA}.",
        suggestion=(
            "Regenerate the case with OpenFOAM Case Generator "
            f"{GENERATOR_VERSION}, which writes schema {SPEC_SCHEMA}."
        ),
    )


def _require_structure(spec: dict[str, Any]) -> None:
    generator = spec.get("generator")
    if not isinstance(generator, str) or not generator:
        raise SpecError(
            'case.json is missing string "generator".',
            suggestion="Regenerate the case. The generator stamps its version into case.json.",
        )
    case_name = spec.get("caseName")
    if not isinstance(case_name, str) or not case_name or "/" in case_name or "\\" in case_name:
        raise SpecError(
            'case.json "caseName" must be a name without slashes.',
            suggestion="Set caseName to a single folder name, such as myCase.",
        )
    version = spec.get("openfoamVersion")
    if isinstance(version, bool) or not isinstance(version, int):
        raise SpecError(
            'case.json "openfoamVersion" must be an integer.',
            suggestion="Use an OpenFOAM version the generator offers, such as 2412 or 12.",
        )
    state = spec.get("state")
    if not isinstance(state, dict):
        raise SpecError(
            'case.json is missing object "state".',
            suggestion="Regenerate the case. validateSpec in the generator checks the physics.",
        )
    state_map = cast(dict[str, Any], state)
    solver = state_map.get("solver")
    if not isinstance(solver, str) or not solver:
        raise SpecError(
            "case.json state.solver must be a string.",
            suggestion="Set state.solver to a solver name. The generator rejects unknown solvers.",
        )
    patches = state_map.get("patches")
    if not isinstance(patches, list):
        raise SpecError(
            'case.json "state.patches" must be an array.',
            suggestion="Each patch needs a name and a role. The generator checks the role names.",
        )
    for index, patch in enumerate(cast(list[object], patches)):
        if not isinstance(patch, dict):
            raise SpecError(
                f"state.patches[{index}] is not an object.",
                suggestion="Each patch needs string fields name and role.",
            )
        patch_map = cast(dict[str, Any], patch)
        name = patch_map.get("name")
        role = patch_map.get("role")
        if not isinstance(name, str) or not name or not isinstance(role, str) or not role:
            raise SpecError(
                f"state.patches[{index}] needs string name and role.",
                suggestion="The generator's validateSpec checks patch names and roles.",
            )
