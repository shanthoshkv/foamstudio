"""First-install setup and Tools > Setup & libraries: venv, libraries, OpenFOAM."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from foamstudio.app.settings import AppSettings
from foamstudio.core import setup_env
from foamstudio.core.runtime.probe import SubprocessProbe

logger = logging.getLogger("foamstudio.setup")


class _Job(QThread):
    line = Signal(str)
    step = Signal(int, int)
    done = Signal(object)

    def __init__(self, fn: Callable[[_Job], object]) -> None:
        super().__init__()
        self._fn = fn

    def log(self, text: str) -> None:
        if sys.stdout:  # console progress; pythonw has no stdout
            print(text, flush=True)
        logger.info("%s", text)
        self.line.emit(text)

    def run(self) -> None:
        try:
            self.done.emit(self._fn(self))
        except Exception as exc:
            self.log(f"ERROR: {exc}")
            self.done.emit(None)


class SetupDialog(QDialog):
    def __init__(
        self, settings: AppSettings, parent: QWidget | None = None, *, tab: int = 0
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._job: _Job | None = None
        self.setObjectName("setupDialog")
        self.setWindowTitle(self.tr("FoamStudio setup"))
        self.resize(820, 620)
        self.autoAll = QRadioButton(
            self.tr("Auto-install OpenFOAM + venv + libraries  (~3.5 GB, 10-20 min)")
        )
        self.autoVenv = QRadioButton(
            self.tr("I install OpenFOAM myself; auto-install venv + libraries  (~600 MB, 2-5 min)")
        )
        self.manual = QRadioButton(self.tr("I install both myself (show commands)"))
        self.autoAll.setChecked(True)
        self.progress = QProgressBar()
        self.logView = QPlainTextEdit(readOnly=True)
        self.logView.setObjectName("setupLog")
        page = QWidget()
        layout = QVBoxLayout(page)
        for w in (self.autoAll, self.autoVenv, self.manual, self.progress, self.logView):
            layout.addWidget(w)
        row = QHBoxLayout()
        for name, label, slot in (
            ("runSetup", self.tr("Run setup"), self._run),
            ("checkLibs", self.tr("Check libraries"), self._check),
            ("installMissing", self.tr("Install missing"), self._install_missing),
            ("detectFoam", self.tr("Auto-locate OpenFOAM"), self._detect),
            ("pickFoam", self.tr("Choose OpenFOAM folder..."), self._pick),
            ("wslHealth", self.tr("WSL health"), self._health),
            ("updateApp", self.tr("Update FoamStudio"), self._update),
            ("cancelSetup", self.tr("Cancel step"), setup_env.cancel),
            ("closeSetup", self.tr("Close"), self.accept),
        ):
            button = QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(lambda _c=False, s=slot: s())
            row.addWidget(button)
        layout.addLayout(row)
        # One window for everything environment-related: install, runtimes, remote machines.
        from foamstudio.ui.runtime_wizard import RuntimeWizard
        from foamstudio.ui.ssh_profiles import SshProfiles

        self.runtimes = RuntimeWizard(settings, self)
        self.runtimes.setWindowFlags(Qt.WindowType.Widget)
        self.runtimes.closeButton.hide()
        self.runtimes.accepted.connect(self.accept)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("setupTabs")
        self.tabs.addTab(page, self.tr("Install"))
        self.tabs.addTab(self.runtimes, self.tr("Runtimes"))
        self.tabs.addTab(SshProfiles(settings, self), self.tr("Remote (SSH)"))
        self.tabs.setCurrentIndex(tab)
        QVBoxLayout(self).addWidget(self.tabs)
        pending = settings._store.value("setup/pending")
        if pending in ("all", "venv"):  # resume after the reboot WSL asked for
            (self.autoAll if pending == "all" else self.autoVenv).setChecked(True)
            QTimer.singleShot(0, self._run)

    def _log(self, text: str) -> None:
        self.logView.appendPlainText(text)
        if text.startswith("[") and "] " in text:  # "[2/3] OpenFOAM" -> progress label
            self.progress.setFormat(text)

    def _step(self, i: int, n: int) -> None:
        self.progress.setRange(0, n)
        self.progress.setValue(i)

    def _start(self, fn: Callable[[_Job], object], on_done: Callable[[object], None]) -> None:
        if self._job is not None and self._job.isRunning():
            return
        job = _Job(fn)
        job.line.connect(self._log)
        job.step.connect(self._step)
        job.done.connect(on_done)
        self._job = job
        job.start()

    def _run(self) -> None:
        self._settings._store.setValue("setup/done", True)
        if self.manual.isChecked():
            self._log("# venv + libraries\n" + setup_env.manual_venv_commands())
            self._log("\n# OpenFOAM\n" + setup_env.manual_openfoam_commands())
            self._log("\nThen use 'Auto-locate OpenFOAM' or 'Choose OpenFOAM folder...'.")
            return
        foam = self.autoAll.isChecked()

        def work(job: _Job) -> object:
            steps = 3 if foam else 2
            job.step.emit(0, steps)
            job.log(f"[1/{steps}] venv + libraries -> {setup_env.venv_dir()}")
            ok = setup_env.install_venv(job.log)
            job.step.emit(1, steps)
            if foam:
                job.log(f"[2/{steps}] OpenFOAM")
                ok = setup_env.install_openfoam(job.log) and ok
                job.step.emit(2, steps)
            job.log(f"[{steps}/{steps}] locating OpenFOAM")
            found = _locate(job)
            job.step.emit(steps, steps)
            job.log("Setup finished." if ok else "Setup finished with errors; see log above.")
            return found, ok

        self._start(work, lambda r: self._finish(r, "all" if foam else "venv"))

    def _finish(self, result: object, mode: str) -> None:
        found, ok = result if isinstance(result, tuple) else (None, False)
        self._settings._store.setValue("setup/pending", "" if ok else mode)
        self._use(found)

    def _update(self) -> None:
        self._start(lambda job: setup_env.update_source(job.log), self._restart)

    def _restart(self, ok: object) -> None:
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication, QMessageBox

        if ok is not True:
            return
        answer = QMessageBox.question(self, "FoamStudio", self.tr("Updated. Restart now?"))
        if answer == QMessageBox.StandardButton.Yes:
            QProcess.startDetached(sys.executable, sys.orig_argv[1:])
            QApplication.quit()

    def _health(self) -> None:
        from foamstudio.core.assist import wsl_health

        runtime = self._settings.load_runtime()
        distro = runtime.distro if runtime and runtime.distro else setup_env.DISTRO

        def work(job: _Job) -> object:
            job.log("\n".join(wsl_health(distro)))
            return None

        self._start(work, lambda _r: None)

    def _check(self) -> None:
        def work(job: _Job) -> object:
            rows = setup_env.check_libs()
            for req, ver in rows:
                job.log(f"{'OK     ' if ver else 'MISSING'} {req:32} {ver or ''}")
            missing = [r for r, v in rows if v is None]
            job.log(f"{len(rows) - len(missing)}/{len(rows)} installed.")
            if missing:
                job.log("Manual: pip install " + " ".join(f'"{r}"' for r in missing))
            return None

        self._start(work, lambda _r: None)

    def _install_missing(self) -> None:
        self._start(lambda job: setup_env.install_venv(job.log, missing_only=True), lambda _r: None)

    def _detect(self) -> None:
        self._start(_locate, self._use)

    def _pick(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("OpenFOAM root (contains etc/bashrc)"), "\\\\wsl.localhost\\"
        )
        if not folder:
            return
        try:
            self._use(setup_env.installation_from_folder(folder))
        except (OSError, ValueError) as exc:
            self._log(str(exc))

    def _use(self, installation: object) -> None:
        from foamstudio.core.runtime.model import Installation

        if not isinstance(installation, Installation):
            return
        self._settings.save_runtime(installation)
        self._settings.set_wizard_done(True)
        self._log(f"Runtime saved: {installation.label()}  ({installation.bashrc})")


def _locate(job: _Job) -> object:
    from foamstudio.core.runtime import detect

    report = detect(SubprocessProbe(), timeout=60)  # native, WSL and Docker
    for note in report.notes:
        job.log(note)
    found = report.installations
    for item in found:
        job.log(f"found {item.label()}  {item.bashrc}")
    if not found:
        job.log("No OpenFOAM found. Use 'Choose OpenFOAM folder...'.")
    return max(found, key=lambda i: (i.kind == "wsl", i.version)) if found else None
