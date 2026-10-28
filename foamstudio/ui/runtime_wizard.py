"""First-run chooser for an external OpenFOAM installation."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from foamstudio.app.settings import AppSettings
from foamstudio.core.paths import state_dir
from foamstudio.core.runtime import bind, detect
from foamstudio.core.runtime.install_offers import install_offers, visible_terminal
from foamstudio.core.runtime.model import (
    CommandResult,
    DetectionReport,
    Installation,
    RuntimeFailure,
    format_argv,
)
from foamstudio.core.runtime.paths import launch_env
from foamstudio.core.runtime.probe import Probe

logger = logging.getLogger("foamstudio.runtime")

_CHECK = "simpleFoam -help"


class _CallThread(QThread):
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.ok.emit(self._fn())
        except Exception as exc:
            self.failed.emit(str(exc))


def _launch(argv: tuple[str, ...]) -> None:
    subprocess.Popen(list(argv), env=launch_env())


class RuntimeWizard(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        detect_fn: Callable[[], DetectionReport] | None = None,
        probe: Probe | None = None,
        platform: str | None = None,
        case_path: Path | None = None,
        launcher: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._probe = probe
        self._platform = sys.platform if platform is None else platform
        self._detect_fn = detect_fn or (lambda: detect(self._probe, platform=self._platform))
        self._launcher = launcher or _launch
        self._case = self._case_dir(case_path)
        self._found: list[Installation] = []
        self._worker: _CallThread | None = None
        self._alive = True
        self.setObjectName("runtimeWizard")
        self.setWindowTitle(self.tr("OpenFOAM runtimes"))
        self.resize(860, 720)
        self._build()
        QTimer.singleShot(0, self.refresh)

    @staticmethod
    def _case_dir(case_path: Path | None) -> Path:
        if case_path is not None:
            return case_path
        path = state_dir() / "runtime-check"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _build(self) -> None:
        self.runtimeList = QListWidget()
        self.runtimeList.setObjectName("runtimeList")
        self.runtimeList.setAccessibleName(self.tr("Installations"))
        self.notesView = self._text("notesView", self.tr("Notes"))
        self.commandView = self._text("commandView", self.tr("Command"))
        self.outputView = self._text("outputView", self.tr("Output"))
        self.offerCombo = QComboBox()
        self.offerCombo.setObjectName("offerCombo")
        self.offerCombo.blockSignals(True)
        for offer in install_offers(self._platform):
            self.offerCombo.addItem(offer.title, offer.command)
        self.offerCombo.blockSignals(False)

        self.refreshButton = self._button("refreshButton", self.tr("Refresh"), self.refresh)
        self.testButton = self._button("testButton", self.tr("Test simpleFoam -help"), self._test)
        self.useButton = self._button("useButton", self.tr("Use this runtime"), self._use)
        self.showInstallButton = self._button(
            "showInstallButton", self.tr("Show install command"), self._show_offer
        )
        self.runInstallButton = self._button(
            "runInstallButton", self.tr("Run install command"), self._run_install
        )
        self.skipButton = self._button("skipButton", self.tr("Skip for now"), self._skip)
        self.closeButton = self._button("closeButton", self.tr("Close"), self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Installations")))
        layout.addWidget(self.runtimeList, 2)
        layout.addWidget(QLabel(self.tr("Notes")))
        layout.addWidget(self.notesView, 1)
        layout.addWidget(QLabel(self.tr("Command")))
        layout.addWidget(self.commandView, 2)
        layout.addWidget(QLabel(self.tr("Output")))
        layout.addWidget(self.outputView, 2)
        layout.addWidget(QLabel(self.tr("Guided install")))
        layout.addWidget(self.offerCombo)
        row = QHBoxLayout()
        for button in (
            self.refreshButton,
            self.testButton,
            self.useButton,
            self.showInstallButton,
            self.runInstallButton,
            self.skipButton,
            self.closeButton,
        ):
            row.addWidget(button)
        layout.addLayout(row)
        self.runtimeList.currentItemChanged.connect(self._on_current_item)
        self.testButton.setEnabled(False)
        self.useButton.setEnabled(False)

    def _text(self, name: str, accessible: str) -> QPlainTextEdit:
        view = QPlainTextEdit()
        view.setObjectName(name)
        view.setAccessibleName(accessible)
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        return view

    def _button(self, name: str, label: str, slot: Callable[[], None]) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName(name)
        button.clicked.connect(lambda _checked=False, slot=slot: slot())
        return button

    def refresh(self) -> None:
        if not self._alive:
            return
        self._start(self._detect_fn, self._apply_report, detect=True)

    def _on_current_item(
        self,
        _current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        self._show_runtime_command()

    def _show_runtime_command(self) -> None:
        installation = self._current()
        self.testButton.setEnabled(installation is not None)
        self.useButton.setEnabled(installation is not None)
        if installation is None:
            return
        try:
            shown = bind(installation, self._probe).describe(_CHECK, self._case)
        except (ValueError, RuntimeFailure) as exc:
            self.commandView.setPlainText(str(exc))
            return
        self.commandView.setPlainText(shown)

    def _test(self) -> None:
        installation = self._current()
        if installation is None:
            self.outputView.setPlainText(self.tr("No runtime selected."))
            return
        runtime = bind(installation, self._probe)
        try:
            plan = runtime.prepare(_CHECK, self._case)
        except (ValueError, RuntimeFailure) as exc:
            logger.error("%s", exc)
            self.commandView.setPlainText(str(exc))
            self.outputView.setPlainText(str(exc))
            return
        self.commandView.setPlainText(plan.display())
        case = self._case

        def go() -> CommandResult:
            return asyncio.run(runtime.execute(plan, case=case, timeout=60))

        self._start(go, self._show_result, detect=False)

    def _show_result(self, result: object) -> None:
        if not self._alive:
            return
        if not isinstance(result, CommandResult):
            self._show_failure(self.tr("Detection returned an unexpected result."))
            return
        text = result.stdout
        if result.stderr:
            text = f"{text}\n{result.stderr}".strip()
        self.outputView.setPlainText(text or self.tr("Command finished with no output."))

    def _apply_report(self, result: object) -> None:
        if not self._alive:
            return
        if not isinstance(result, DetectionReport):
            self._show_failure(self.tr("Detection returned an unexpected result."), detect=True)
            return
        self._found = list(result.installations)
        self.runtimeList.clear()
        for index, installation in enumerate(self._found):
            item = QListWidgetItem(installation.label())
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.runtimeList.addItem(item)
        self.notesView.setPlainText("\n\n".join(result.notes) or self.tr("No notes."))
        if self._found:
            self.runtimeList.setCurrentRow(0)
        else:
            self.testButton.setEnabled(False)
            self.useButton.setEnabled(False)

    def _use(self) -> None:
        installation = self._current()
        if installation is None:
            self.outputView.setPlainText(self.tr("No runtime selected."))
            return
        try:
            self._settings.save_runtime(installation)
            self._settings.set_wizard_done(True)
        except OSError as exc:
            logger.error("%s", exc)
            self.outputView.setPlainText(str(exc))
            return
        self.accept()

    def _skip(self) -> None:
        try:
            self._settings.set_wizard_done(True)
        except OSError as exc:
            logger.error("%s", exc)
            self.outputView.setPlainText(str(exc))
            return
        self.reject()

    def _show_offer(self) -> None:
        command = self.offerCombo.currentData()
        if isinstance(command, str):
            self.commandView.setPlainText(command)

    def _run_install(self) -> None:
        command = self.offerCombo.currentData()
        if not isinstance(command, str) or not command.strip():
            return
        argv = visible_terminal(command, self._platform)
        shown = format_argv(argv)
        self.commandView.setPlainText(f"{shown}\n\n{command}")
        try:
            self._launcher(argv)
        except Exception as exc:
            message = f"{shown}\n\n{exc}\n\nRun the command yourself."
            logger.error("%s", message)
            self.outputView.setPlainText(message)

    def _current(self) -> Installation | None:
        item = self.runtimeList.currentItem()
        if item is None:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int) and 0 <= index < len(self._found):
            return self._found[index]
        return None

    def _start(
        self,
        fn: Callable[[], object],
        on_ok: Callable[[object], None],
        *,
        detect: bool,
    ) -> None:
        if not self._alive:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        worker = _CallThread(fn)
        self._worker = worker
        worker.ok.connect(lambda result, on_ok=on_ok: self._deliver(result, on_ok))
        worker.failed.connect(
            lambda message, detect=detect: self._show_failure(message, detect=detect)
        )
        worker.finished.connect(lambda worker=worker: self._reap(worker))
        worker.start()

    def _deliver(self, result: object, on_ok: Callable[[object], None]) -> None:
        if self._alive:
            on_ok(result)

    def _show_failure(self, message: str, *, detect: bool = False) -> None:
        if not self._alive:
            return
        logger.error("%s", message)
        self.outputView.setPlainText(message)
        if detect:
            self.notesView.setPlainText(message)

    def _reap(self, worker: _CallThread) -> None:
        if self._worker is worker:
            self._worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        self._alive = False
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.blockSignals(True)
            if worker.isRunning():
                worker.wait(3000)
        super().closeEvent(event)
