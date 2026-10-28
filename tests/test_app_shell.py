from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from foamstudio.app.i18n.loader import install_translators
from foamstudio.app.main import main
from foamstudio.app.mainwindow import MainWindow
from foamstudio.app.settings import AppSettings
from foamstudio.app.theme import load_qss


@pytest.fixture
def window(qtbot, tmp_path: Path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = MainWindow(AppSettings(store))
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_shell_layout(window: MainWindow) -> None:
    labels = [window.project_tree.topLevelItem(i).text(0) for i in range(6)]
    assert labels == ["Geometry", "Mesh", "Setup", "Run", "Results", "Reports"]
    assert window.centralWidget() is window.viewer
    assert window.project_dock.objectName() == "projectDock"
    assert window.properties_dock.objectName() == "propertiesDock"
    assert window.console_dock.objectName() == "consoleDock"
    assert window.console_tabs.count() == 4
    assert window.console_tabs.tabText(0) == "Log"
    assert window.console_tabs.tabText(3) == "Problems"
    assert window.viewer.text() == "No geometry loaded."
    assert window.isVisible()


def test_log_tab_shows_records(window: MainWindow) -> None:
    logging.getLogger("foamstudio").error("hello-from-test")
    assert "hello-from-test" in window.log_view.toPlainText()


def test_theme_and_font(window: MainWindow, qapp: QApplication, tmp_path: Path) -> None:
    window.set_theme("light")
    assert "#f4f6f8" in qapp.styleSheet()
    window.set_theme("dark")
    assert "#00c896" in qapp.styleSheet()
    window.increase_font()
    assert window._model.font_point_size == 11
    assert qapp.font().pointSize() == 11
    saved = (tmp_path / "settings.ini").read_text(encoding="utf-8")
    assert "11" in saved
    window.set_expert_mode(True)
    saved = (tmp_path / "settings.ini").read_text(encoding="utf-8")
    assert "true" in saved.lower()
    assert "Dictionary editor" in window.statusBar().currentMessage()
    window.set_expert_mode(False)
    assert window.statusBar().currentMessage() == "Expert mode is off."


def test_bad_saved_theme_is_reported(
    qtbot, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    store.setValue("theme", "neon")
    store.sync()
    caplog.set_level(logging.ERROR, logger="foamstudio")
    widget = MainWindow(AppSettings(store))
    qtbot.addWidget(widget)
    assert widget._model.theme == "dark"
    assert "neon" in caplog.text


def test_stylesheets_exist() -> None:
    assert "#000000" in load_qss("dark")
    assert "#f4f6f8" in load_qss("light")
    with pytest.raises(ValueError, match="neon"):
        load_qss("neon")


def test_english_catalog_is_well_formed() -> None:
    root = Path(__file__).parents[1] / "foamstudio" / "app" / "i18n" / "foamstudio_en.ts"
    tree = ET.parse(root).getroot()
    assert tree.tag == "TS"
    assert tree.attrib["language"] == "en"
    sources = [node.text for node in tree.iter("source")]
    assert "Geometry" in sources
    assert "No geometry loaded." in sources
    assert "New project..." in sources
    assert "Write case" in sources
    assert "Case generator ready." in sources


def test_missing_translation_is_logged(qapp: QApplication, monkeypatch, caplog) -> None:
    monkeypatch.setenv("FOAMSTUDIO_LANG", "zz")
    caplog.set_level(logging.ERROR, logger="foamstudio")
    assert install_translators(qapp) == []
    assert "foamstudio_zz.qm" in caplog.text


def test_self_test_launches() -> None:
    assert main(["--self-test"]) == 0
