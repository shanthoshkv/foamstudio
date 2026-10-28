"""Audit the environment that CI installs. Skips when pip-licenses is absent."""

from __future__ import annotations

from pathlib import Path

import pytest

from foamstudio.core.licenses import main


def test_installed_packages_fit_gpl3(tmp_path: Path) -> None:
    pytest.importorskip("piplicenses")
    out = tmp_path / "THIRD_PARTY_LICENSES.txt"
    assert main(["--check", "--write", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Incompatible: 0" in text
    assert "PySide6" in text or "PySide6_Essentials" in text
