"""Section panels stay in the properties dock. Import is what replaces the viewer."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QLabel

from foamstudio.app.mainwindow import MainWindow
from foamstudio.app.settings import AppSettings
from foamstudio.core.project import create_project
from foamstudio.ui.residual_plot import ResidualPlot


@pytest.fixture
def window(qtbot, tmp_path: Path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = MainWindow(AppSettings(store))
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_tree_clicks_keep_the_placeholder(window: MainWindow) -> None:
    for index in range(6):
        item = window.project_tree.topLevelItem(index)
        window._on_project_item(item, 0)
        assert window.centralWidget() is window.viewer
        assert window.viewer.text() == "No geometry loaded."
    assert window.properties_dock.widget().objectName() == "reportPanel"
    window.open_dictionary()
    assert window.properties_dock.widget().objectName() == "dictEditor"


def test_import_replaces_the_viewer_and_picks_a_patch(window: MainWindow, tmp_path: Path) -> None:
    path = tmp_path / "inlet.stl"
    path.write_text(
        "solid inlet\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid inlet\n",
        encoding="utf-8",
    )
    window.import_geometry(path)
    view = window.centralWidget()
    assert view is not window.viewer
    assert view.objectName() == "viewer3d"
    assert isinstance(view, QLabel) is False
    panel = window._geometry_panel
    assert panel is not None
    item = panel._list.item(0)
    assert item is not None
    panel._list.itemClicked.emit(item)
    assert "inlet" in window.statusBar().currentMessage()


def test_mesh_report_and_crash_preference(window: MainWindow, tmp_path: Path) -> None:
    project = create_project(tmp_path / "job", app_version="0.9.0")
    window._adopt_project(project)
    window._on_project_item(window.project_tree.topLevelItem(1), 0)
    window.write_block_mesh()
    written = project.case_dir / "system" / "blockMeshDict"
    assert "blockMeshDict" in written.read_text(encoding="utf-8")
    window._on_project_item(window.project_tree.topLevelItem(5), 0)
    window.write_report(pdf=False)
    html = (project.root / "report.html").read_text(encoding="utf-8")
    assert "No solver log was found" in html
    window._on_project_item(window.project_tree.topLevelItem(4), 0)
    window.write_paraview_state()
    assert (project.case_dir / "case.foam").is_file()
    theme = window._model.theme
    window.set_crash_reports(True)
    assert window._model.crash_reports is True
    assert window._model.theme == theme
    window.set_theme("light" if theme == "dark" else "dark")
    assert window._model.crash_reports is True


def test_residual_summary_without_drawing(monkeypatch: pytest.MonkeyPatch) -> None:
    plot = ResidualPlot()
    assert plot.summary.text() == "No residuals yet."
    monkeypatch.setattr(ResidualPlot, "_try_plot", lambda _self, _samples: None)
    plot.set_samples([])
    assert plot.summary.text() == "No residuals yet."


def test_pdf_report(tmp_path: Path) -> None:
    from foamstudio.ui.report_panel import write_pdf

    destination = tmp_path / "report.pdf"
    write_pdf("<html><body><h1>Cavity</h1></body></html>", destination)
    assert destination.stat().st_size >= 50
