from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction

from foamstudio.app.main import main
from foamstudio.app.mainwindow import MainWindow
from foamstudio.app.settings import AppSettings

_GOLDEN = Path(__file__).parents[1] / "tests" / "golden" / "v2412.json"


@pytest.fixture
def window(qtbot, tmp_path: Path) -> MainWindow:
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = MainWindow(AppSettings(store))
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def _action(window: MainWindow, name: str) -> QAction:
    action = window.findChild(QAction, name)
    assert isinstance(action, QAction)
    return action


def test_project_actions_exist(window: MainWindow) -> None:
    assert _action(window, "actionNewProject").text() == "New project..."
    assert _action(window, "actionOpenProject").text() == "Open project..."
    assert _action(window, "actionWriteCase").text() == "Write case"


def test_headless_setup_does_not_load_webengine(window: MainWindow) -> None:
    window.open_setup()
    assert "QtWebEngineWidgets" not in sys.modules
    assert window.statusBar().currentMessage() == "Generator view stays closed in headless mode."
    assert window._setup is None


def test_create_and_open_project(window: MainWindow, tmp_path: Path) -> None:
    root = tmp_path / "study"
    project = window.create_project(root)
    assert project is not None
    assert window.statusBar().currentMessage() == "Project created"
    assert (root / "foamstudio.json").is_file()
    assert (root / "case").is_dir()
    assert (root / "geometry").is_dir()
    assert window.create_project(root) is None
    assert "already a FoamStudio project" in window.log_view.toPlainText()
    assert window.open_project_path(tmp_path / "missing") is None
    assert "foamstudio.json" in window.log_view.toPlainText()
    assert window.open_project_path(root) is not None
    assert window.statusBar().currentMessage() == "Project opened"


def test_write_without_project_is_loud(qtbot, window: MainWindow) -> None:
    with qtbot.waitSignal(window.case_write_failed, timeout=2000):
        window.write_case()
    assert "Create or open a project" in window.log_view.toPlainText()
    assert "foamstudio.json" in window.log_view.toPlainText()


def test_write_case_from_saved_spec(qtbot, window: MainWindow, tmp_path: Path) -> None:
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    project = window.create_project(tmp_path / "study")
    assert project is not None
    spec = golden["2412_simpleFoam"]["case.json"]
    (project.case_dir / "case.json").write_text(spec, encoding="utf-8")
    with qtbot.waitSignal(window.case_written, timeout=120000) as blocker:
        window.write_case()
    assert blocker.args
    assert "headless.js" in blocker.args[0]
    assert "--apply-spec" in blocker.args[0]
    written = (project.case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    assert "FoamFile" in written
    manifest = json.loads((project.root / "foamstudio.json").read_text(encoding="utf-8"))
    assert "headless.js" in manifest["commands"][-1]["command"]
    assert window.findChild(QAction, "actionWriteCase").isEnabled()


def test_write_case_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    spec_path = tmp_path / "case.json"
    spec_path.write_text(golden["2412_icoFoam"]["case.json"], encoding="utf-8")
    project = tmp_path / "proj"
    assert main(["--write-case", str(spec_path), "--project", str(project)]) == 0
    captured = capsys.readouterr()
    assert "headless.js" in captured.out
    assert (project / "case" / "system" / "controlDict").is_file()
    assert (project / "foamstudio.json").is_file()
    assert main(["--write-case", str(spec_path)]) == 2
    assert main(["--project", str(project)]) == 2
