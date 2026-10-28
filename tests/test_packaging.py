from __future__ import annotations

import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

from foamstudio.generator.resources import webengine_files

_SPEC = Path(__file__).parents[1] / "packaging" / "foamstudio.spec"


def test_pyinstaller_spec_collects_webengine_and_drops_charts() -> None:
    text = _SPEC.read_text(encoding="utf-8")
    excludes = text.split("excludes=[", 1)[1].split("]", 1)[0]
    hidden = text.split("hiddenimports=[", 1)[1].split("]", 1)[0]
    assert "QtWebEngine" not in excludes
    assert "QtCharts" in excludes
    assert "QtDataVisualization" in excludes
    assert "QtWebEngineWidgets" in hidden
    assert "QtWebChannel" in hidden
    assert "openfoam_case_generator.html" in text
    assert "headless.js" in text


def test_charts_modules_are_not_imported() -> None:
    root = Path(__file__).parents[1] / "foamstudio"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "QtCharts" not in text, path.name
        assert "QtDataVisualization" not in text, path.name


def _qt_release(dist: str) -> tuple[str, str, str]:
    parts = version(dist).split(".")
    return parts[0], parts[1], parts[2]


def test_addons_match_essentials_and_ship_webengine() -> None:
    essentials = _qt_release("PySide6_Essentials")
    addons = _qt_release("PySide6_Addons")
    webengine = _qt_release("PySide6_WebEngine")
    assert essentials == addons == webengine
    files = webengine_files()
    assert files["process"].is_file()
    assert files["icudtl"].is_file()
    assert files["resources_pak"].is_file()


@pytest.mark.skipif(
    os.environ.get("FOAMSTUDIO_PYINSTALLER") != "1",
    reason="Set FOAMSTUDIO_PYINSTALLER=1 to build the one-folder WebEngine bundle.",
)
def test_pyinstaller_bundle_contains_webengine_process(tmp_path: Path) -> None:
    repo = Path(__file__).parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            str(tmp_path / "dist"),
            "--workpath",
            str(tmp_path / "build"),
            str(repo / "packaging" / "foamstudio.spec"),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-4000:] + completed.stderr[-4000:]
    bundle = tmp_path / "dist" / "foamstudio"
    matches = list(bundle.rglob("QtWebEngineProcess*"))
    assert matches, "PyInstaller bundle has no QtWebEngineProcess"
    assert any(path.is_file() for path in matches)
    assert (bundle / "openfoam_case_generator.html").is_file()
