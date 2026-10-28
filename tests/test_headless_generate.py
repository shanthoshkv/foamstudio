from __future__ import annotations

import json
from pathlib import Path

import pytest

from foamstudio.core.spec import SpecError, parse_spec
from foamstudio.generator.headless import (
    GeneratorFailure,
    apply_many,
    apply_spec_text,
    first_difference,
    generate_table,
    relativize,
)
from foamstudio.generator.solvers import SOLVERS, TAGGED_CASES, golden_key

_GOLDEN = Path(__file__).parent / "golden" / "v2412.json"


def _golden() -> dict[str, dict[str, str]]:
    data = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _assert_case(got: dict[str, str], expected: dict[str, str], label: str) -> None:
    for key in sorted(set(got) | set(expected)):
        if key not in expected:
            pytest.fail(f"{label}/{key}: added")
        if key not in got:
            pytest.fail(f"{label}/{key}: removed")
        if got[key] != expected[key]:
            pytest.fail(f"{label}/{key}: {first_difference(expected[key], got[key])}")


def test_solver_acceptance_set_has_25_names() -> None:
    assert len(SOLVERS) == 25
    assert len(set(SOLVERS)) == 25


def test_generate_table_matches_golden() -> None:
    golden = _golden()
    produced = generate_table("gen_fn.js", ["2412"])
    keys = [golden_key(solver) for solver in SOLVERS]
    keys.extend(TAGGED_CASES)
    for key in keys:
        assert key in produced, key
        case = produced[key]
        assert isinstance(case, dict)
        files = case["files"]
        assert isinstance(files, dict)
        _assert_case(relativize(files, key), golden[key], key)


def test_apply_many_matches_golden() -> None:
    golden = _golden()
    keys = [golden_key(solver) for solver in SOLVERS]
    keys.extend(TAGGED_CASES)
    jobs: list[tuple[str, str]] = []
    for key in keys:
        spec_text = golden[key]["case.json"]
        spec = json.loads(spec_text)
        jobs.append((str(spec["caseName"]), spec_text))
    generated = apply_many(jobs)
    assert len(generated) == len(jobs)
    for key, case in zip(keys, generated, strict=True):
        _assert_case(relativize(case.files, case.case_name), golden[key], f"apply {key}")
        assert "headless.js" in case.command
        assert "--apply-many" in case.command


def test_apply_spec_text_round_trip_one_solver() -> None:
    golden = _golden()
    spec_text = golden["2412_simpleFoam"]["case.json"]
    spec = json.loads(spec_text)
    generated = apply_spec_text(spec_text, case_name=str(spec["caseName"]))
    _assert_case(
        relativize(generated.files, generated.case_name),
        golden["2412_simpleFoam"],
        "2412_simpleFoam",
    )
    assert "--apply-spec" in generated.command


def test_unknown_solver_is_a_generator_failure() -> None:
    golden = _golden()
    spec = json.loads(golden["2412_simpleFoam"]["case.json"])
    spec["state"]["solver"] = "fooFoam"
    with pytest.raises(GeneratorFailure) as caught:
        apply_spec_text(json.dumps(spec), case_name="myCase")
    assert "fooFoam" in caught.value.log_tail or "unknown solver" in caught.value.log_tail
    assert "headless.js" in caught.value.command
    assert caught.value.suggestion


def test_missing_node_names_the_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing-node"
    monkeypatch.setenv("FOAMSTUDIO_NODE", str(missing))
    spec = {
        "schema": 1,
        "generator": "2.2.0",
        "openfoamVersion": 2412,
        "caseName": "myCase",
        "state": {"solver": "simpleFoam", "patches": []},
    }
    parse_spec(spec)
    with pytest.raises(GeneratorFailure) as caught:
        apply_spec_text(json.dumps(spec), case_name="myCase")
    assert caught.value.returncode == 127
    assert "Node.js" in caught.value.suggestion
    assert "missing-node" in caught.value.command


def test_bad_schema_does_not_need_node() -> None:
    with pytest.raises(SpecError, match="schema 99"):
        parse_spec({"schema": 99})
