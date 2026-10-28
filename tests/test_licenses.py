from __future__ import annotations

import json
from pathlib import Path

import pytest

from foamstudio.core.licenses import (
    format_report,
    license_compatible,
    main,
    normalise_entries,
)


@pytest.mark.parametrize(
    ("expression", "compatible"),
    [
        ("MIT", True),
        ("MIT License", True),
        ("BSD-3-Clause", True),
        ("Apache-2.0", True),
        ("Apache Software License", True),
        ("LGPL-3.0-only", True),
        ("GNU Lesser General Public License v2.1", True),
        ("GPL-3.0-only", True),
        ("GNU General Public License v3 (GPLv3)", True),
        ("GPL-2.0-or-later", True),
        ("GPLv2+", True),
        ("MPL-2.0", True),
        ("BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0", True),
        ("CC0-1.0", True),
        ("Python Software Foundation License", True),
        ("MIT OR GPL-2.0-only", True),
        ("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only", True),
        (
            "GNU Library or Lesser General Public License (LGPL); Other/Proprietary License",
            True,
        ),
        ("GPL-2.0-only", False),
        ("GNU General Public License v2", False),
        ("MIT AND GPL-2.0-only", False),
        ("Proprietary", False),
        ("Apache License 1.1", False),
        ("UNKNOWN", False),
        ("", False),
        ("Some Random Licence", False),
    ],
)
def test_gpl3_compatibility(expression: str, compatible: bool) -> None:
    assert license_compatible(expression).compatible is compatible


def test_pyside_grant_is_the_lgpl_alternative() -> None:
    verdict = license_compatible("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only")
    assert verdict.compatible is True
    assert "LGPL-3.0-only" in verdict.reason


def test_report_lists_incompatible_packages(tmp_path: Path) -> None:
    raw = [
        {"Name": "Good", "Version": "1", "License": "MIT"},
        {"Name": "Bad", "Version": "2", "License": "GPL-2.0-only"},
    ]
    report, bad = format_report(normalise_entries(raw))
    assert "Good 1" in report
    assert "INCOMPATIBLE" in report
    assert len(bad) == 1
    source = tmp_path / "in.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    out = tmp_path / "THIRD_PARTY_LICENSES.txt"
    assert main(["--input", str(source), "--write", str(out), "--check"]) == 1
    assert "GPL-2.0-only" in out.read_text(encoding="utf-8")


def test_clean_report_exits_zero(tmp_path: Path) -> None:
    source = tmp_path / "in.json"
    source.write_text(
        json.dumps([{"Name": "Good", "Version": "1", "License": "BSD-3-Clause"}]),
        encoding="utf-8",
    )
    out = tmp_path / "out.txt"
    assert main(["--input", str(source), "--write", str(out), "--check"]) == 0
    assert "Incompatible: 0" in out.read_text(encoding="utf-8")


def test_broken_json_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "in.json"
    source.write_text("{", encoding="utf-8")
    assert main(["--input", str(source), "--check"]) == 2
    assert "Licence audit failed" in capsys.readouterr().err


def test_core_modules_do_not_import_qt() -> None:
    root = Path(__file__).parents[1] / "foamstudio" / "core"
    sources = list(root.rglob("*.py"))
    assert len(sources) >= 8
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "PySide" not in text, path.name
        assert "PyQt" not in text, path.name
