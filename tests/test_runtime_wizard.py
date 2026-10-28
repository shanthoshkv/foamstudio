"""Runtime wizard with a fake detector. It must not probe the real machine."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog

from foamstudio.app.mainwindow import MainWindow
from foamstudio.app.settings import AppSettings
from foamstudio.core.runtime.model import DetectionReport, Installation
from foamstudio.core.runtime.probe import Completed
from foamstudio.ui.runtime_wizard import RuntimeWizard

_WSL = Installation(
    kind="wsl",
    flavour="esi",
    version="2412",
    bashrc="/usr/lib/openfoam/openfoam2412/etc/bashrc",
    distro="Ubuntu-24.04",
)
_NATIVE = Installation(
    kind="native",
    flavour="esi",
    version="2412",
    bashrc="/usr/lib/openfoam/openfoam2412/etc/bashrc",
)


class ScriptProbe:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd=None, env=None, timeout=None):  # noqa: ANN001
        command = tuple(argv)
        self.calls.append(command)
        return Completed(command, self.returncode, self.stdout, self.stderr)


def _settings(tmp_path: Path) -> AppSettings:
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return AppSettings(store)


def _wizard(qtbot, settings: AppSettings, **kwargs) -> RuntimeWizard:  # noqa: ANN001
    dialog = RuntimeWizard(settings, **kwargs)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


def test_wizard_lists_wsl_without_a_dollar(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    report = DetectionReport((_WSL,), ("WSL note",))
    wizard = _wizard(
        qtbot,
        _settings(tmp_path),
        detect_fn=lambda: report,
        probe=ScriptProbe(),
        platform="win32",
        case_path=Path("C:/cases/check"),
    )
    qtbot.waitUntil(lambda: wizard.runtimeList.count() == 1 and wizard.useButton.isEnabled())
    assert "2412" in wizard.runtimeList.item(0).text()
    assert "wsl" in wizard.runtimeList.item(0).text()
    command = wizard.commandView.toPlainText()
    assert "wsl.exe" in command
    assert "$" not in command
    assert "WSL note" in wizard.notesView.toPlainText()
    qtbot.mouseClick(wizard.showInstallButton, Qt.MouseButton.LeftButton)
    assert wizard.commandView.toPlainText().strip() == "wsl --install -d Ubuntu-24.04"


def test_use_persists_the_runtime(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    settings = _settings(tmp_path)
    wizard = _wizard(
        qtbot,
        settings,
        detect_fn=lambda: DetectionReport((_WSL,), ()),
        probe=ScriptProbe(),
        platform="win32",
        case_path=Path("C:/cases/check"),
    )
    qtbot.waitUntil(lambda: wizard.useButton.isEnabled())
    qtbot.mouseClick(wizard.useButton, Qt.MouseButton.LeftButton)
    assert wizard.result() == QDialog.DialogCode.Accepted
    assert settings.load_runtime() == _WSL
    assert settings.wizard_done() is True


def test_failure_shows_command_and_suggestion(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    case = tmp_path / "cavity"
    case.mkdir()
    probe = ScriptProbe(127, stderr="simpleFoam: command not found\n")
    wizard = _wizard(
        qtbot,
        _settings(tmp_path),
        detect_fn=lambda: DetectionReport((_NATIVE,), ()),
        probe=probe,
        platform="linux",
        case_path=case,
    )
    qtbot.waitUntil(lambda: wizard.testButton.isEnabled())
    qtbot.mouseClick(wizard.testButton, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: "Command failed" in wizard.outputView.toPlainText())
    output = wizard.outputView.toPlainText()
    assert "simpleFoam -help" in output
    assert "OpenFOAM did not provide this command" in output
    assert "bash" in wizard.commandView.toPlainText()
    assert probe.calls


def test_successful_check_shows_stdout(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    case = tmp_path / "cavity"
    case.mkdir()
    wizard = _wizard(
        qtbot,
        _settings(tmp_path),
        detect_fn=lambda: DetectionReport((_NATIVE,), ()),
        probe=ScriptProbe(0, stdout="Usage: simpleFoam [OPTIONS]\n"),
        platform="linux",
        case_path=case,
    )
    qtbot.waitUntil(lambda: wizard.testButton.isEnabled())
    qtbot.mouseClick(wizard.testButton, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: "Usage: simpleFoam" in wizard.outputView.toPlainText())


def test_install_launcher_failure_is_shown(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    def launcher(argv: tuple[str, ...]) -> None:
        raise OSError("no terminal")

    wizard = _wizard(
        qtbot,
        _settings(tmp_path),
        detect_fn=lambda: DetectionReport((), ()),
        probe=ScriptProbe(),
        platform="win32",
        case_path=Path("C:/cases/check"),
        launcher=launcher,
    )
    qtbot.mouseClick(wizard.runInstallButton, Qt.MouseButton.LeftButton)
    output = wizard.outputView.toPlainText()
    assert "no terminal" in output
    assert "Run the command yourself." in output
    assert "cmd.exe" in wizard.commandView.toPlainText()
    assert "wsl --install -d Ubuntu-24.04" in wizard.commandView.toPlainText()


def test_skip_marks_the_wizard_done(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    settings = _settings(tmp_path)
    wizard = _wizard(
        qtbot,
        settings,
        detect_fn=lambda: DetectionReport((), ("none",)),
        probe=ScriptProbe(),
        platform="linux",
        case_path=tmp_path,
    )
    qtbot.mouseClick(wizard.skipButton, Qt.MouseButton.LeftButton)
    assert settings.wizard_done() is True
    assert wizard.result() == QDialog.DialogCode.Rejected


def test_saved_runtime_round_trip_and_garbage(
    qtbot, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert qtbot is not None
    settings = _settings(tmp_path)
    settings.save_runtime(_WSL)
    assert settings.load_runtime() == _WSL
    settings.set_wizard_done(True)
    assert settings.wizard_done() is True

    store = settings._store
    caplog.set_level(logging.ERROR, logger="foamstudio")
    store.setValue("runtime", "{")
    store.sync()
    assert settings.load_runtime() is None
    assert "Saved runtime was ignored" in caplog.text

    store.setValue(
        "runtime",
        json.dumps({"kind": "ssh", "flavour": "esi", "version": "2412", "bashrc": "/b"}),
    )
    store.sync()
    assert settings.load_runtime() is None
    assert "ssh" in caplog.text

    store.setValue("wizard_done", "banana")
    store.sync()
    assert settings.wizard_done() is False
    assert "banana" in caplog.text


def test_runtimes_action_and_headless_prompt(qtbot, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    window = MainWindow(_settings(tmp_path))
    qtbot.addWidget(window)
    action = window.findChild(QAction, "actionRuntimes")
    assert action is not None
    assert action.text() == "Runtimes..."
    called: list[str] = []
    monkeypatch.setattr(window, "open_runtime_wizard", lambda: called.append("open"))
    window.maybe_prompt_runtime()
    assert called == []
    monkeypatch.delenv("FOAMSTUDIO_HEADLESS", raising=False)
    window.maybe_prompt_runtime()
    assert called == ["open"]
    window._store.save_runtime(_NATIVE)
    called.clear()
    window.maybe_prompt_runtime()
    assert called == []
    window._store.set_wizard_done(True)
    window._store._store.remove("runtime")
    window.maybe_prompt_runtime()
    assert called == []
