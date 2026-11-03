"""Dock shell: project tree, viewer, properties, console."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from foamstudio import APP_LICENSE, __version__
from foamstudio.app.settings import AppSettings
from foamstudio.app.theme import load_icon, load_qss, ui_font
from foamstudio.core.project import Project, ProjectError
from foamstudio.core.project import create_project as create_project_at
from foamstudio.core.project import open_project as open_project_at
from foamstudio.core.runtime.model import Installation

if TYPE_CHECKING:
    from foamstudio.core.jobs import JobQueue
from foamstudio.core.settings_model import (
    DEFAULT_FONT_PT,
    MAX_FONT_PT,
    MIN_FONT_PT,
    SettingsModel,
)
from foamstudio.core.spec import GENERATOR_VERSION
from foamstudio.ui.dict_editor import DictEditor
from foamstudio.ui.mesh_panel import MeshPanel
from foamstudio.ui.patch_panel import PatchPanel
from foamstudio.ui.post_panel import PostPanel
from foamstudio.ui.report_panel import ReportPanel
from foamstudio.ui.residual_plot import ResidualPlot
from foamstudio.ui.run_panel import RunPanel
from foamstudio.ui.setup_panel import SetupPanel
from foamstudio.ui.tools_panel import ToolsPanel
from foamstudio.ui.viewer3d import Viewer3D

logger = logging.getLogger("foamstudio")


def _duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{max(minutes, 1)} min"


def _end_time(case: Path) -> float | None:
    control = case / "system" / "controlDict"
    if not control.is_file():
        return None
    found = re.search(r"^endTime\s+([0-9.eE+-]+);", control.read_text(encoding="utf-8"), re.M)
    return float(found.group(1)) if found else None


_SECTIONS = ("Geometry", "Mesh", "Setup", "Run", "Results", "Reports")
_CONSOLE_TABS = (
    ("Log", ""),
    (
        "Residuals",
        "No residuals yet. Start a run (Run panel or dashboard) and they plot here live.",
    ),
    (
        "Monitors",
        "No monitors yet. Force coefficients and probes appear here once a run writes them.",
    ),
    ("Problems", "No problems."),
)


class _LogBridge(QObject):
    message = Signal(str)


class _Background(QThread):
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object], parent: QObject) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.ok.emit(self._fn())
        except Exception as exc:
            self.failed.emit(str(exc))


class _QtLogHandler(logging.Handler):
    def __init__(self, bridge: _LogBridge) -> None:
        super().__init__()
        self.bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        self.bridge.message.emit(self.format(record))


class MainWindow(QMainWindow):
    case_written = Signal(str)
    case_write_failed = Signal(str)

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = settings
        self._model = SettingsModel()
        self._log_handler: _QtLogHandler | None = None
        self._project: Project | None = None
        self._setup: SetupPanel | None = None
        self.setup_dock: QDockWidget | None = None
        self._surface = None
        self._geometry_panel: PatchPanel | None = None
        self._mesh_panel: MeshPanel | None = None
        self._run_panel: RunPanel | None = None
        self._post_panel: PostPanel | None = None
        self._report_panel: ReportPanel | None = None
        self._dict_editor: DictEditor | None = None
        self._residual_plot: ResidualPlot | None = None
        self._viewer3d: Viewer3D | None = None
        self._tools: ToolsPanel | None = None
        self._dashboard: QWidget | None = None
        self._jobs = None
        self._solver: _Background | None = None
        self._render: _Background | None = None
        self._writer: _Background | None = None
        self._write_action: QAction | None = None
        self.setWindowTitle(self.tr("FoamStudio"))
        self.setWindowIcon(load_icon())
        self.resize(1280, 800)
        self.setDockNestingEnabled(True)
        self.setAnimated(False)
        self._build_viewer()
        self._build_project()
        self._build_properties()
        self._build_console()
        self._build_menus()
        self._attach_log_handler()
        self._model = self._store.load()
        self._apply_model(self._model, persist=False)
        self.statusBar().showMessage(self.tr("No project open"))
        version = QLabel(f"{__version__}  {APP_LICENSE}")
        version.setObjectName("versionLabel")
        self.statusBar().addPermanentWidget(version)
        logger.info("FoamStudio %s started", __version__)

    def _build_viewer(self) -> None:
        self.viewer = QLabel(self.tr("No geometry loaded."))
        self.viewer.setObjectName("viewer")
        self.viewer.setAccessibleName(self.tr("Viewer"))
        self.viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer.setWordWrap(True)
        self.setCentralWidget(self.viewer)

    def _build_project(self) -> None:
        self.project_tree = QTreeWidget()
        self.project_tree.setObjectName("projectTree")
        self.project_tree.setAccessibleName(self.tr("Project"))
        self.project_tree.setHeaderHidden(True)
        for name in _SECTIONS:
            QTreeWidgetItem(self.project_tree, [self.tr(name)])
        self.project_tree.itemClicked.connect(self._on_project_item)
        self.project_dock = self._dock("projectDock", self.tr("Project"), self.project_tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.project_dock)

    def _build_properties(self) -> None:
        self.properties = QLabel(self.tr("Nothing selected."))
        self.properties.setObjectName("properties")
        self.properties.setAccessibleName(self.tr("Properties"))
        self.properties.setWordWrap(True)
        self.properties.setMargin(12)
        self.properties_dock = self._dock("propertiesDock", self.tr("Properties"), self.properties)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

    def _build_console(self) -> None:
        self.console_tabs = QTabWidget()
        self.console_tabs.setObjectName("consoleTabs")
        self.console_tabs.setAccessibleName(self.tr("Console"))
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setAccessibleName(self.tr("Log"))
        self.console_tabs.addTab(self.log_view, self.tr("Log"))
        for name, placeholder in _CONSOLE_TABS[1:]:
            label = QLabel(self.tr(placeholder))
            label.setObjectName(name.lower())
            label.setMargin(12)
            label.setWordWrap(True)
            self.console_tabs.addTab(label, self.tr(name))
        self.console_dock = self._dock("consoleDock", self.tr("Console"), self.console_tabs)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.console_dock)

    def _dock(self, object_name: str, title: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(object_name)
        dock.setAccessibleName(title)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        return dock

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu(self.tr("File"))
        new_action = QAction(self.tr("New project..."), self)
        new_action.setObjectName("actionNewProject")
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(lambda _checked=False: self.new_project_dialog())
        open_action = QAction(self.tr("Open project..."), self)
        open_action.setObjectName("actionOpenProject")
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(lambda _checked=False: self.open_project_dialog())
        self._write_action = QAction(self.tr("Write case"), self)
        self._write_action.setObjectName("actionWriteCase")
        self._write_action.setShortcut(QKeySequence.StandardKey.Save)
        self._write_action.triggered.connect(lambda _checked=False: self.write_case())
        import_action = QAction(self.tr("Import geometry..."), self)
        import_action.setObjectName("actionImportGeometry")
        import_action.triggered.connect(lambda _checked=False: self.import_geometry_dialog())
        file_menu.addAction(new_action)
        airfoil_action = QAction(self.tr("New airfoil case..."), self)
        airfoil_action.setObjectName("actionNewAirfoil")
        airfoil_action.triggered.connect(lambda _checked=False: self.new_airfoil_dialog())
        file_menu.addAction(airfoil_action)
        file_menu.addAction(open_action)
        file_menu.addAction(import_action)
        file_menu.addAction(self._write_action)
        file_menu.addSeparator()
        quit_action = QAction(self.tr("Quit"), self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu(self.tr("View"))
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._dark_action = self._theme_action(self.tr("Dark theme"), "dark")
        self._light_action = self._theme_action(self.tr("Light theme"), "light")
        view_menu.addAction(self._dark_action)
        view_menu.addAction(self._light_action)
        view_menu.addSeparator()

        larger = QAction(self.tr("Increase font size"), self)
        larger.setShortcut(QKeySequence.StandardKey.ZoomIn)
        larger.triggered.connect(self.increase_font)
        smaller = QAction(self.tr("Decrease font size"), self)
        smaller.setShortcut(QKeySequence.StandardKey.ZoomOut)
        smaller.triggered.connect(self.decrease_font)
        reset = QAction(self.tr("Reset font size"), self)
        reset.setShortcut(QKeySequence("Ctrl+0"))
        reset.triggered.connect(self.reset_font)
        view_menu.addAction(larger)
        view_menu.addAction(smaller)
        view_menu.addAction(reset)
        view_menu.addSeparator()

        self._expert_action = QAction(self.tr("Expert mode"), self)
        self._expert_action.setCheckable(True)
        self._expert_action.toggled.connect(self.set_expert_mode)
        view_menu.addAction(self._expert_action)
        self._crash_action = QAction(self.tr("Send crash reports"), self)
        self._crash_action.setCheckable(True)
        self._crash_action.setObjectName("actionCrashReports")
        self._crash_action.toggled.connect(self.set_crash_reports)
        view_menu.addAction(self._crash_action)
        dashboard = QAction(self.tr("Dashboard"), self)
        dashboard.setObjectName("actionDashboard")
        dashboard.setShortcut("Ctrl+D")
        dashboard.triggered.connect(lambda _checked=False: self.open_dashboard())
        view_menu.addAction(dashboard)

        tools_menu = self.menuBar().addMenu(self.tr("Tools"))
        runtimes = QAction(self.tr("Runtimes..."), self)
        runtimes.setObjectName("actionRuntimes")
        runtimes.triggered.connect(lambda _checked=False: self.open_runtime_wizard())
        tools_action = QAction(self.tr("Workspace tools..."), self)
        tools_action.setObjectName("actionWorkspaceTools")
        tools_action.triggered.connect(lambda _checked=False: self.open_tools())
        dictionary = QAction(self.tr("Dictionary editor..."), self)
        dictionary.setObjectName("actionDictionary")
        dictionary.triggered.connect(lambda _checked=False: self.open_dictionary())
        setup = QAction(self.tr("Setup && libraries..."), self)
        setup.setObjectName("actionSetup")
        setup.triggered.connect(lambda _checked=False: self.open_install_setup())
        tools_menu.addAction(setup)
        tools_menu.addAction(runtimes)
        tools_menu.addAction(tools_action)
        tools_menu.addAction(dictionary)
        for name, label, key, slot in (
            ("actionPalette", self.tr("Command palette..."), "Ctrl+K", self.open_palette),
            ("actionConsole", self.tr("Python console..."), "Ctrl+Shift+P", self.open_console),
            ("actionVSCode", self.tr("Open case in VS Code"), "", self.open_vscode),
            (
                "actionPhysics",
                self.tr("Physics && templates..."),
                "Ctrl+Shift+F",
                self.open_physics,
            ),
        ):
            act = QAction(label, self)
            act.setObjectName(name)
            act.setShortcut(key)
            act.triggered.connect(lambda _c=False, s=slot: s())
            tools_menu.addAction(act)

        help_menu = self.menuBar().addMenu(self.tr("Help"))
        about = QAction(self.tr("About"), self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)
        for name, label, key, slot in (
            ("actionShortcuts", self.tr("Keyboard shortcuts"), "F1", self.open_shortcuts),
            ("actionReport", self.tr("Report a problem..."), "", self.report_problem),
        ):
            act = QAction(label, self)
            act.setObjectName(name)
            act.setShortcut(key)
            act.triggered.connect(lambda _c=False, s=slot: s())
            help_menu.addAction(act)
        licence = QAction(self.tr("Enter licence key..."), self)
        licence.setObjectName("actionLicence")
        licence.triggered.connect(lambda _checked=False: self.enter_licence_dialog())
        help_menu.addAction(licence)

    def _theme_action(self, label: str, theme: str) -> QAction:
        action = QAction(label, self)
        action.setCheckable(True)
        action.setData(theme)
        action.triggered.connect(lambda: self.set_theme(theme))
        self._theme_group.addAction(action)
        return action

    def _attach_log_handler(self) -> None:
        bridge = _LogBridge(self)
        bridge.message.connect(self._append_log)
        handler = _QtLogHandler(bridge)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        self._log_handler = handler

    def _append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())  # always follow the newest line

    def _apply_model(self, model: SettingsModel, *, persist: bool) -> None:
        model.validate()
        self._model = model
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(load_qss(model.theme))
            app.setFont(ui_font(model.font_point_size))
        self._dark_action.blockSignals(True)
        self._light_action.blockSignals(True)
        self._expert_action.blockSignals(True)
        self._crash_action.blockSignals(True)
        self._dark_action.setChecked(model.theme == "dark")
        self._light_action.setChecked(model.theme == "light")
        self._expert_action.setChecked(model.expert_mode)
        self._crash_action.setChecked(model.crash_reports)
        self._dark_action.blockSignals(False)
        self._light_action.blockSignals(False)
        self._expert_action.blockSignals(False)
        self._crash_action.blockSignals(False)
        if persist:
            self._store.save(model)

    def set_theme(self, theme: str) -> None:
        self._apply_model(replace(self._model, theme=theme), persist=True)

    def increase_font(self) -> None:
        self._step_font(1, self.tr("Maximum font size"))

    def decrease_font(self) -> None:
        self._step_font(-1, self.tr("Minimum font size"))

    def reset_font(self) -> None:
        if self._model.font_point_size == DEFAULT_FONT_PT:
            self.statusBar().showMessage(self.tr("Font size reset"))
            return
        self._apply_model(replace(self._model, font_point_size=DEFAULT_FONT_PT), persist=True)
        self.statusBar().showMessage(self.tr("Font size reset"))

    def set_expert_mode(self, enabled: bool) -> None:
        self._apply_model(replace(self._model, expert_mode=enabled), persist=True)
        if enabled:
            self.statusBar().showMessage(
                self.tr("Expert mode is on. Dictionary editor is under Tools.")
            )
        else:
            self.statusBar().showMessage(self.tr("Expert mode is off."))

    def new_project_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("New project folder"), self._projects_root()
        )
        if folder:
            self.create_project(Path(folder))

    def _projects_root(self) -> str:
        """WSL runtime -> start inside the distro's home so cases sit on the Linux disk."""
        from foamstudio.core.setup_env import wsl_projects_dir

        runtime = self._store.load_runtime()
        if runtime is None or runtime.kind != "wsl":
            return ""
        return str(wsl_projects_dir(runtime.distro) or "")

    def new_airfoil_dialog(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        code, ok = QInputDialog.getText(
            self, self.tr("Airfoil"), self.tr("NACA 4-digit code"), text="0012"
        )
        if not ok:
            return
        alpha, ok = QInputDialog.getDouble(
            self, self.tr("Airfoil"), self.tr("Angle of attack (deg)"), 0.0, -20.0, 25.0, 2
        )
        if not ok:
            return
        reynolds, ok = QInputDialog.getDouble(
            self, self.tr("Airfoil"), self.tr("Chord Reynolds number"), 6e6, 1e4, 1e9, 0
        )
        if not ok:
            return
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("New project folder"), self._projects_root()
        )
        if folder:
            self.create_airfoil(Path(folder), code.strip(), alpha, reynolds)

    def create_airfoil(
        self, root: Path, code: str, alpha: float, reynolds: float
    ) -> Project | None:
        """NACA C-mesh, Spalart-Allmaras, fixed-U far field, live Cl/Cd and a Cd/Cl stop."""
        from foamstudio.core import runinfo
        from foamstudio.generator.write_case import write_airfoil

        project = self.create_project(root)
        if project is None:
            return None
        try:
            # 89,600 cells at scale 1: pick ranks from that before the mesh exists
            procs = runinfo.suggest_processes(89_600)
            paths, _command = write_airfoil(
                project, code, alpha, reynolds, app_version=__version__, processes=procs
            )
        except Exception as exc:
            logger.error("%s", exc)
            self.statusBar().showMessage(str(exc).splitlines()[0])
            return None
        if self._run_panel is not None:
            self._run_panel.processes.setValue(procs)
        logger.info("NACA %s, alpha %g, Re %g: wrote %s files", code, alpha, reynolds, len(paths))
        self.statusBar().showMessage(self.tr("Airfoil case written. Run it from the Run panel."))
        return project

    def open_project_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.tr("Open project folder"))
        if folder:
            self.open_project_path(Path(folder))

    def create_project(self, root: Path) -> Project | None:
        try:
            project = create_project_at(root, app_version=__version__)
        except ProjectError as exc:
            self._report_project_error(exc)
            return None
        self._adopt_project(project)
        self.statusBar().showMessage(self.tr("Project created"))
        logger.info("Project created: %s", project.root)
        return project

    def open_project_path(self, root: Path) -> Project | None:
        try:
            project = open_project_at(root)
        except ProjectError as exc:
            self._report_project_error(exc)
            return None
        self._adopt_project(project)
        self.statusBar().showMessage(self.tr("Project opened"))
        logger.info("Project opened: %s", project.root)
        return project

    def open_setup(self) -> None:
        if os.environ.get("FOAMSTUDIO_HEADLESS") == "1":
            logger.error(
                "Generator view stays closed in headless mode.\n\n"
                "Unset FOAMSTUDIO_HEADLESS to open the case generator."
            )
            self.statusBar().showMessage(self.tr("Generator view stays closed in headless mode."))
            return
        self._ensure_setup_panel()
        assert self._setup is not None
        try:
            self._setup.load_generator()
        except Exception as exc:
            logger.error("%s", exc)
            self.statusBar().showMessage(str(exc).splitlines()[0])
            return
        assert self.setup_dock is not None
        self.setup_dock.show()
        self.setup_dock.raise_()
        # The generator is a full web form; give it most of the window width.
        self.resizeDocks([self.setup_dock], [int(self.width() * 0.6)], Qt.Orientation.Horizontal)

    def write_case(self) -> None:
        if self._writer is not None and self._writer.isRunning():
            self._report_write_failure(
                "A case write is already running.\n\n"
                "Wait for it to finish. The command is in the log."
            )
            return
        if self._project is None:
            self._report_write_failure(
                "Create or open a project before writing the case.\n\n"
                "File → New project... creates case/, geometry/, and foamstudio.json."
            )
            return
        session = None if self._setup is None else self._setup.session
        if session is not None:
            from foamstudio.generator.bridge import GeneratorSession

            if isinstance(session, GeneratorSession):
                command = "QWebEngine runJavaScript buildCaseFiles"
                logger.info("Writing case with %s", command)
                self.statusBar().showMessage(self.tr("Writing case..."))
                self._set_write_enabled(False)
                session.build_current_async(
                    lambda payload: self._write_js_payload(payload, command)
                )
                return
        spec_path = self._project.case_dir / "case.json"
        if not spec_path.is_file():
            self._report_write_failure(
                "There is no generator page and no case/case.json to write.\n\n"
                "Open Setup to load the case generator, or run "
                "foamstudio --write-case case.json --project <folder>."
            )
            return
        from foamstudio.core.spec import SpecError, load_spec
        from foamstudio.generator.headless import apply_command

        try:
            spec = load_spec(spec_path.read_text(encoding="utf-8-sig"))
        except (OSError, SpecError) as exc:
            self._report_write_failure(str(exc))
            return
        command = apply_command(spec_path, case_name=str(spec["caseName"]))
        logger.info("Writing case with %s", command)
        self.statusBar().showMessage(self.tr("Writing case..."))
        project = self._project
        app_version = __version__

        def work() -> str:
            from foamstudio.generator.write_case import write_spec_file

            paths, used = write_spec_file(project, spec_path, app_version=app_version)
            return f"Wrote {len(paths)} files into {project.case_dir}\n{used}"

        self._start_worker(work)

    def _on_project_item(self, item: QTreeWidgetItem, _column: int) -> None:
        label = item.text(0)
        if label == self.tr("Setup"):
            self.open_setup()
        elif label == self.tr("Geometry"):
            self._show_geometry_panel()
        elif label == self.tr("Mesh"):
            self._show_mesh_panel()
        elif label == self.tr("Run"):
            self._show_run_panel()
        elif label == self.tr("Results"):
            self._show_post_panel()
        elif label == self.tr("Reports"):
            self._show_report_panel()

    def _adopt_project(self, project: Project) -> None:
        self._project = project
        self.setWindowTitle(f"{self.tr('FoamStudio')} — {project.root.name}")
        self.project_dock.setToolTip(str(project.root))
        self._reattach()

    def _detached_queue(self) -> JobQueue | None:
        from foamstudio.core.jobs import JobQueue
        from foamstudio.core.runtime import bind
        from foamstudio.core.runtime.paths import DETACHED

        assert self._project is not None
        marker = self._project.case_dir / DETACHED
        installation = self._project_runtime() or self._store.load_runtime()
        if not marker.is_file() or installation is None:
            return None
        queue = JobQueue(bind(installation), self._project.case_dir)
        queue.pid = int(json.loads(marker.read_text(encoding="utf-8"))["pid"])
        return queue

    def _reattach(self) -> bool:
        """A background run started before FoamStudio closed: follow its log again."""
        from foamstudio.core.runtime.paths import DETACHED

        assert self._project is not None
        case = self._project.case_dir
        marker = case / DETACHED
        logs = sorted(case.glob("log.*"), key=lambda p: p.stat().st_mtime)
        if not marker.is_file() or not logs or time.time() - logs[-1].stat().st_mtime > 300:
            return False
        if self._run_panel is None:
            self._show_run_panel()
        self._residual_timer = QTimer(self)
        self._residual_timer.timeout.connect(self._refresh_residuals)
        self._residual_timer.start(2000)
        # after the caller's own "Project opened" message
        message = self.tr("Reattached to a background run")
        QTimer.singleShot(0, lambda: self.statusBar().showMessage(message))
        logger.info("Reattached to the background run in %s", case)
        return True

    def _report_project_error(self, exc: ProjectError) -> None:
        logger.error("%s", exc)
        self.statusBar().showMessage(exc.message)

    def _ensure_setup_panel(self) -> None:
        if self._setup is not None:
            return
        self._setup = SetupPanel(self)
        self._setup.write_requested.connect(self.write_case)
        self.setup_dock = self._dock("setupDock", self.tr("Setup"), self._setup)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.setup_dock)
        # Share the full right column with Properties instead of a corner split.
        self.tabifyDockWidget(self.properties_dock, self.setup_dock)

    def _report_write_failure(self, message: str) -> None:
        logger.error("%s", message)
        first = message.splitlines()[0] if message else self.tr("Write case failed")
        self.statusBar().showMessage(first)
        self.case_write_failed.emit(message)

    def _write_js_payload(self, payload: object, command: str) -> None:
        if not isinstance(payload, dict) or not payload.get("ok") or self._project is None:
            self._set_write_enabled(True)
            detail = payload.get("error") if isinstance(payload, dict) else payload
            self._report_write_failure(
                "The case generator failed.\n"
                f"{command}\n\n"
                f"{detail}\n\n"
                "Fix the problem reported above. Semantic checks come from validateSpec "
                "in the generator page."
            )
            return
        raw_files = payload.get("files")
        if not isinstance(raw_files, dict):
            self._set_write_enabled(True)
            self._report_write_failure(
                f"The case generator returned no files.\n{command}\n\n"
                "buildCaseFiles should return a map of path to text."
            )
            return
        files = {str(key): str(value) for key, value in raw_files.items()}
        case_name = str(payload.get("caseName") or "case")
        generator_version = str(payload.get("generator") or GENERATOR_VERSION)
        openfoam = payload.get("openfoamVersion")
        project = self._project
        app_version = __version__

        def work() -> str:
            from foamstudio.core.project import write_case_files

            paths = write_case_files(
                project,
                files,
                case_name=case_name,
                command=command,
                app_version=app_version,
                generator_version=generator_version,
                openfoam_version=None if openfoam is None else str(openfoam),
            )
            return f"Wrote {len(paths)} files into {project.case_dir}\n{command}"

        self._start_worker(work)

    def _start_worker(self, work: Callable[[], object]) -> None:
        self._set_write_enabled(False)
        self._writer = _Background(work, self)
        self._writer.ok.connect(self._on_case_ok)
        self._writer.failed.connect(self._on_case_fail)
        self._writer.start()

    def _on_case_ok(self, result: object) -> None:
        text = str(result)
        logger.info("%s", text)
        self.statusBar().showMessage(self.tr("Case written"))
        self._set_write_enabled(True)
        self.case_written.emit(text)

    def _on_case_fail(self, message: str) -> None:
        self._set_write_enabled(True)
        self._report_write_failure(message)

    def _set_write_enabled(self, enabled: bool) -> None:
        if self._write_action is not None:
            self._write_action.setEnabled(enabled)
        if self._setup is not None:
            self._setup.write_button.setEnabled(enabled)

    def open_install_setup(self, tab: int = 0) -> None:
        from foamstudio.ui.setup_dialog import SetupDialog

        if SetupDialog(self._store, parent=self, tab=tab).exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage(self.tr("Runtime saved"))

    def open_runtime_wizard(self) -> None:
        self.open_install_setup(tab=1)  # runtimes live in the setup window now

    def maybe_prompt_runtime(self) -> None:
        if os.environ.get("FOAMSTUDIO_HEADLESS") == "1":
            return
        if self._store.wizard_done() or self._store.load_runtime() is not None:
            return
        self.open_runtime_wizard()

    def set_crash_reports(self, enabled: bool) -> None:
        self._apply_model(replace(self._model, crash_reports=enabled), persist=True)
        self.statusBar().showMessage(
            self.tr("Crash reports stay on this computer until an upload URL is set.")
        )

    def import_geometry_dialog(self) -> None:
        chosen, _selected = QFileDialog.getOpenFileName(
            self,
            self.tr("Import geometry"),
            "",
            self.tr("Geometry (*.stl *.obj *.msh *.step *.stp);;All files (*.*)"),
        )
        if chosen:
            self.import_geometry(Path(chosen))

    def import_geometry(self, path: Path) -> None:
        from foamstudio.core.geometry import ImportFailure, import_path

        try:
            surface = import_path(path)
        except (ImportFailure, OSError) as exc:
            logger.error("%s", exc)
            self.statusBar().showMessage(str(exc).splitlines()[0])
            return
        self._surface = surface
        self._show_geometry_panel()
        assert self._geometry_panel is not None
        self._geometry_panel.set_surface(surface)
        view = Viewer3D(self)
        view.set_surface(surface)
        self._viewer3d = view
        self._set_centre(view)
        self.statusBar().showMessage(self.tr("Geometry loaded"))
        logger.info("Imported %s (%s patches)", path, len(surface.patches))

    def _show_geometry_panel(self) -> None:
        if self._geometry_panel is None:
            self._geometry_panel = PatchPanel(self)
            self._geometry_panel.patch_picked.connect(self._on_patch)
        if self._surface is not None:
            self._geometry_panel.set_surface(self._surface)
        self.properties_dock.setWidget(self._geometry_panel)

    def _on_patch(self, name: str) -> None:
        from foamstudio.core.geometry import ImportFailure, generator_patches

        if self._surface is None:
            return
        try:
            rows = generator_patches(self._surface, name)
        except ImportFailure as exc:
            logger.error("%s", exc)
            return
        logger.info("Patch selection %s", json.dumps(rows))
        session = None if self._setup is None else self._setup.session
        if session is not None and os.environ.get("FOAMSTUDIO_HEADLESS") != "1":
            try:
                session.set_patches(rows)
            except Exception as exc:
                logger.error("%s", exc)
        self.statusBar().showMessage(name)

    def _show_mesh_panel(self) -> None:
        if self._mesh_panel is None:
            self._mesh_panel = MeshPanel(self)
            self._mesh_panel.write_button.clicked.connect(
                lambda _checked=False: self.write_block_mesh()
            )
            self._mesh_panel.send_button.clicked.connect(
                lambda _checked=False: self.send_patch_roles()
            )
            self._mesh_panel.snappy_button.clicked.connect(
                lambda _checked=False: self.write_snappy_mesh()
            )
            self._mesh_panel.quality_button.clicked.connect(
                lambda _checked=False: self.show_mesh_quality()
            )
        self.properties_dock.setWidget(self._mesh_panel)

    def show_mesh_quality(self) -> str:
        """Cells checkMesh flagged (Allrun runs it; sets land in constant/polyMesh/sets)."""
        from foamstudio.core.runinfo import bad_cells

        if self._project is None:
            logger.error("Open a project first. The mesh quality sets live in its case folder.")
            return ""
        sets = bad_cells(self._project.case_dir)
        if not sets:
            text = self.tr("No checkMesh sets. Run the case (Allrun runs checkMesh) or checkMesh.")
        else:
            text = "; ".join(f"{name}: {len(ids)} cells" for name, ids in sets.items())
        view = self._viewer3d or Viewer3D(self)
        if self._viewer3d is None:
            self._viewer3d = view
            self._set_centre(view)
        view.show_cells(self._project.case_dir, sets, text)
        logger.info("Mesh quality: %s", text)
        return text

    def write_block_mesh(self) -> None:
        from foamstudio.core.mesh import MeshFailure, block_mesh_dict, patch_rows

        if self._mesh_panel is None:
            return
        if self._project is None:
            logger.error(
                "Create or open a project before writing a mesh.\n\n"
                "File → New project... creates case/ and foamstudio.json."
            )
            self.statusBar().showMessage(self.tr("Create or open a project"))
            return
        kind = self._mesh_panel.kind.currentText()
        try:
            text = block_mesh_dict(kind, **self._mesh_panel.params())  # type: ignore[arg-type]
        except MeshFailure as exc:
            logger.error("%s", exc)
            return
        target = self._project.case_dir / "system" / "blockMeshDict"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        # Plain blockMesh case now: a leftover snappy setup would make Run add snappyHexMesh.
        (target.parent / "snappyHexMeshDict").unlink(missing_ok=True)
        logger.info("Wrote %s", target)
        self.statusBar().showMessage(self.tr("blockMeshDict written"))
        # The case's boundary conditions must name the same patches as the mesh.
        self._mesh_panel.set_patches(patch_rows(text))
        self.send_patch_roles()

    def write_snappy_mesh(self) -> None:
        """External-flow mesh around the imported surface: background box + snappyHexMesh."""
        import trimesh

        from foamstudio.core.mesh import MeshFailure, snappy_around

        if self._mesh_panel is None:
            return
        if self._project is None or self._surface is None:
            logger.error(
                "Open a project and import a surface first.\n\n"
                "File → Import geometry... loads an STL/OBJ/STEP; snappyHexMesh meshes around it."
            )
            self.statusBar().showMessage(self.tr("Import geometry first"))
            return
        points: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        for triangle in self._surface.triangles:
            start = len(points)
            points.extend((triangle.a, triangle.b, triangle.c))
            faces.append((start, start + 1, start + 2))
        stl_name = f"{self._surface.name or 'body'}.stl".replace(" ", "_")
        try:
            block, snappy, rows = snappy_around(points, stl_name)
        except MeshFailure as exc:
            logger.error("%s", exc)
            return
        case = self._project.case_dir
        surface_dir = case / "constant" / "triSurface"
        surface_dir.mkdir(parents=True, exist_ok=True)
        trimesh.Trimesh(vertices=points, faces=faces, process=True).export(surface_dir / stl_name)
        (case / "system").mkdir(parents=True, exist_ok=True)
        system = case / "system"
        (system / "blockMeshDict").write_text(block, encoding="utf-8", newline="\n")
        (system / "snappyHexMeshDict").write_text(snappy, encoding="utf-8", newline="\n")
        logger.info("Wrote blockMeshDict, snappyHexMeshDict and triSurface/%s", stl_name)
        self.statusBar().showMessage(self.tr("snappyHexMesh setup written"))
        self._mesh_panel.set_patches(rows)
        self.send_patch_roles()

    def send_patch_roles(self) -> None:
        """Push the (possibly edited) patch roles from the Mesh panel into the generator."""
        if self._mesh_panel is None:
            return
        rows = self._mesh_panel.patch_rows()
        session = None if self._setup is None else self._setup.session
        if session is not None and os.environ.get("FOAMSTUDIO_HEADLESS") != "1":
            try:
                session.set_patches(rows)
                logger.info("Generator patches set from the mesh: %s", json.dumps(rows))
            except Exception as exc:
                logger.error("%s", exc)
        else:
            logger.info(
                "Open Setup before Write case so the generator gets these patches: %s",
                ", ".join(row["name"] for row in rows),
            )

    def _show_run_panel(self) -> None:
        if self._run_panel is None:
            self._run_panel = RunPanel(self)
            self._run_panel.start_button.clicked.connect(lambda _checked=False: self.start_solver())
            self._run_panel.stop_button.clicked.connect(lambda _checked=False: self.stop_solver())
            self._run_panel.continue_button.clicked.connect(
                lambda _checked=False: self.start_solver(resume=True)
            )
            self._update_run_info(suggest=True)
        self.properties_dock.setWidget(self._run_panel)

    def _update_run_info(self, log_text: str | None = None, *, suggest: bool = False) -> None:
        from foamstudio.core import runinfo

        panel = self._run_panel
        if panel is None or self._project is None:
            return
        case = self._project.case_dir
        cells = runinfo.cell_count(case)
        cores = runinfo.physical_cores()
        lines = []
        if cells:
            best = runinfo.suggest_processes(cells, cores)
            if suggest and panel.processes.value() == 1:
                panel.processes.setValue(best)
            lines.append(
                self.tr("Mesh %1 cells, about %2 GB. Suggested processes %3 (%4 physical cores).")
                .replace("%1", f"{cells:,}")
                .replace("%2", f"{runinfo.memory_gb(cells):.1f}")
                .replace("%3", str(best))
                .replace("%4", str(cores))
            )
        if log_text:
            end = _end_time(case)
            p = runinfo.progress(log_text, end)
            if p is not None:
                eta = "" if p.eta_seconds is None else f", ETA {_duration(p.eta_seconds)}"
                lines.append(f"t = {p.iteration:g}, {p.per_second:.3g} /s{eta}")
                timer = getattr(self, "_residual_timer", None)
                if (self._solver is not None and self._solver.isRunning()) or (
                    timer and timer.isActive()
                ):
                    self.statusBar().showMessage(f"Running: {lines[-1]}")
        panel.info.setText("\n".join(lines) or self.tr("No mesh yet."))

    def start_solver(
        self,
        *,
        resume: bool = False,
        commands: list[tuple[str, str]] | None = None,
        workdir: Path | None = None,
    ) -> None:
        """Allrun (default), a resume, or explicit (command, name) steps in workdir."""
        from foamstudio.core.jobs import JobQueue, logged
        from foamstudio.core.runtime import bind

        if self._run_panel is None:
            self._show_run_panel()
        if self._run_panel is None:
            return
        if self._solver is not None and self._solver.isRunning():
            logger.error("A solver job is already running.\n\nStop it before starting another.")
            return
        if self._project is None:
            logger.error(
                "Create or open a project before running.\n\n"
                "File → New project... creates the case folder."
            )
            self.statusBar().showMessage(self.tr("Create or open a project"))
            return
        installation = self._project_runtime() or self._store.load_runtime()
        if installation is None:
            logger.error("No runtime is saved.\n\nTools → Runtimes... and choose an installation.")
            self.statusBar().showMessage(self.tr("No runtime is saved"))
            return
        from foamstudio.core.licence import status

        allowed, message = status()
        if not allowed:
            logger.error("%s", message)
            self.statusBar().showMessage(message)
            return
        from foamstudio.core.assist import git_snapshot, validate_case

        problems = validate_case(self._project.case_dir)
        if problems and os.environ.get("FOAMSTUDIO_HEADLESS") != "1":
            logger.warning("Pre-run check:\n%s", "\n".join(problems))
            answer = QMessageBox.warning(
                self,
                self.tr("Pre-run check"),
                "\n".join(problems[:15]) + "\n\nRun anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        extra = self._project.case_dir / "system" / "foamstudioFunctions"
        control = self._project.case_dir / "system" / "controlDict"
        if extra.is_file() and control.is_file():  # Physics > Analysis outputs
            from foamstudio.core.physics import include_functions

            control.write_text(include_functions(control.read_text()), newline="\n")
        rev = git_snapshot(self._project.case_dir, f"run {time.strftime('%Y-%m-%d %H:%M:%S')}")
        if rev:
            logger.info("Case setup committed as %s", rev)
        solver = self._run_panel.solver.text().strip() or "simpleFoam"
        queue = JobQueue(bind(installation), workdir or self._project.case_dir)
        snappy = (self._project.case_dir / "system" / "snappyHexMeshDict").is_file()
        if commands:
            for command, name in commands:
                queue.add(logged(command, name), name=name)
        elif resume:
            end = self._run_panel.end_time.text().strip()
            if end:
                from foamstudio.core.units import parse_quantity

                try:  # "2 min" or "0.5 h" become seconds of simulated time
                    end = f"{parse_quantity(end, 'time'):g}"
                except ValueError as exc:
                    self.statusBar().showMessage(str(exc))
                    return
            queue.add_resume(
                solver, parallel=self._run_panel.processes.value(), end_time=end or None
            )
        else:
            queue.add_allrun(
                solver,
                parallel=self._run_panel.processes.value(),
                mesh="snappyHexMesh" if snappy else "blockMesh",
            )
        self._jobs = queue
        if self._run_panel.detached.isChecked() and not commands and not resume:
            try:
                pid = queue.launch_detached(logged("bash ./Allrun", "Allrun"))
            except Exception as exc:
                logger.error("%s", exc)
                return
            logger.info("Background Allrun started (pid %s); it keeps running if you close", pid)
            self.statusBar().showMessage(self.tr("Running in the background"))
            self._residual_timer = QTimer(self)
            self._residual_timer.timeout.connect(self._refresh_residuals)
            self._residual_timer.start(2000)
            return
        self._run_started = time.time()
        self._run_label = ", ".join(job.name for job in queue.jobs)
        logger.info("Running %s", self._run_label)

        def work() -> str:
            results = queue.run_blocking(live=True)
            failed = [job for job in results if job.status == "failed"]
            if failed:
                job = failed[0]
                detail = (
                    f"Command failed ({job.returncode}).\n{job.command}\n\n"
                    f"{job.log_tail}\n\n{job.suggestion}"
                )
                raise RuntimeError(detail)
            return "\n".join(f"{job.status} {job.name}" for job in results)

        self.statusBar().showMessage(self.tr("Running"))
        self._solver = _Background(work, self)
        self._solver.ok.connect(self._solver_ok)
        self._solver.failed.connect(self._solver_fail)
        self._solver.start()
        # Live residuals: re-read the solver log while the job runs.
        self._residual_timer = QTimer(self)
        self._residual_timer.timeout.connect(self._refresh_residuals)
        self._residual_timer.start(2000)

    def _refresh_residuals(self) -> None:
        # ponytail: re-parses the whole log each tick; tail-follow if logs reach 100s of MB
        if self._project is None or self._run_panel is None:
            return
        solver = self._run_panel.solver.text().strip() or "simpleFoam"
        log = self._project.case_dir / f"log.{solver}"
        if not log.is_file():  # e.g. the case runs icoFoam or foamRun, not the panel's solver
            found = sorted(
                [
                    *self._project.case_dir.glob("log.*Foam"),
                    *self._project.case_dir.glob("log.foamRun"),
                ],
                key=lambda p: p.stat().st_mtime,
            )
            log = found[-1] if found else log
        if log.is_file():
            text = log.read_text(encoding="utf-8", errors="replace")
            self.show_residuals(text)
            self._update_run_info(text)
            if self._tools is not None:
                self._tools.set_monitor(text)

    def _stop_residual_timer(self) -> None:
        timer = getattr(self, "_residual_timer", None)
        if timer is not None:
            timer.stop()

    def stop_solver(self) -> None:
        queue = self._jobs
        if queue is None and self._project is not None:
            queue = self._detached_queue()
        if queue is None:
            logger.error("There is no solver job to stop.\n\nRun the case before using Stop.")
            return
        argv = queue.cancel()
        if argv is not None:
            subprocess.run(list(argv), check=False)
            logger.info("Kill %s", " ".join(argv))
        self.statusBar().showMessage(self.tr("Stop requested"))

    def _record(self, status: str) -> None:
        from foamstudio.core.workspace import record_run

        if self._project is not None and getattr(self, "_run_started", None):
            record_run(
                self._project.case_dir, self._run_label, status, self._run_started, time.time()
            )
        if self._tools is not None:
            self._tools.refresh_case()

    def _solver_ok(self, result: object) -> None:
        self._record("succeeded")
        logger.info("%s", result)
        self.statusBar().showMessage(self.tr("Run finished"))
        self._stop_residual_timer()
        self._refresh_residuals()
        self._notify(self.tr("Run finished"), str(result)[:200])

    def _solver_fail(self, message: str) -> None:
        from foamstudio.core.assist import explain_foam_error

        self._record("failed")
        hint = explain_foam_error(message)
        logger.error("%s%s", message, f"\n\nLikely fix: {hint}" if hint else "")
        self.statusBar().showMessage(hint or self.tr("Run failed"))
        self._stop_residual_timer()
        self._notify(self.tr("Run failed"), hint or message.splitlines()[0][:200])

    def _notify(self, title: str, text: str) -> None:
        """Tray toast so a long run can be left in the background."""
        from PySide6.QtWidgets import QSystemTrayIcon

        if not QSystemTrayIcon.isSystemTrayAvailable() or self.isActiveWindow():
            return
        if getattr(self, "_tray", None) is None:
            self._tray = QSystemTrayIcon(self.windowIcon(), self)
            self._tray.show()
        self._tray.showMessage(title, text)

    def open_physics(self) -> None:
        from foamstudio.ui.physics_window import PhysicsWindow

        win = PhysicsWindow(self, self)
        self._physics = win
        if self._viewer3d is not None:  # 3D picks fill the named-selection box
            self._viewer3d.on_pick = lambda lo, hi: (win.set_pick_box(lo, hi), win.raise_())
            self._viewer3d.pick_button.setEnabled(self._viewer3d._plot is not None)
        win.show()

    def open_palette(self) -> None:
        from foamstudio.ui.extras import CommandPalette

        CommandPalette(self).exec()

    def open_shortcuts(self) -> None:
        from foamstudio.ui.extras import shortcut_sheet

        shortcut_sheet(self).exec()

    def open_console(self) -> None:
        from foamstudio.ui.extras import PythonConsole

        case = self._project.case_dir if self._project else None
        self._console = PythonConsole({"window": self, "project": self._project, "case": case})
        self._console.show()

    def open_vscode(self) -> None:
        from foamstudio.core.assist import vscode_argv

        if self._project is None:
            self.statusBar().showMessage(self.tr("Create or open a project"))
            return
        try:
            subprocess.Popen(vscode_argv(self._project.case_dir), shell=sys.platform == "win32")
        except OSError as exc:
            self.statusBar().showMessage(f"VS Code: {exc}")

    def report_problem(self) -> None:
        from PySide6.QtWidgets import QApplication

        from foamstudio.core.assist import support_bundle

        path = support_bundle(
            Path.home() / "Desktop" if (Path.home() / "Desktop").is_dir() else Path.home()
        )
        QApplication.clipboard().setText(str(path))
        QMessageBox.information(
            self,
            "FoamStudio",
            f"Logs zipped to\n{path}\n\nPath copied. Attach it to a GitHub issue.",
        )

    def _show_post_panel(self) -> None:
        if self._post_panel is None:
            self._post_panel = PostPanel(self)
            self._post_panel.export_button.clicked.connect(
                lambda _checked=False: self.write_paraview_state()
            )
            self._post_panel.render_button.clicked.connect(
                lambda _checked=False: self.render_paraview()
            )
        self.properties_dock.setWidget(self._post_panel)

    def write_paraview_state(self) -> None:
        from foamstudio.core.post.paraview import (
            ParaViewFailure,
            pvpython_script,
            write_foam,
        )

        if self._project is None:
            logger.error("Create or open a project before writing a ParaView state.")
            self.statusBar().showMessage(self.tr("Create or open a project"))
            return
        case = self._project.case_dir
        try:
            foam = write_foam(case)
        except ParaViewFailure as exc:
            logger.error("%s", exc)
            return
        state = case / f"{case.name}.pvsm"
        script = case / "pvpython_export.py"
        runtime = self._store.load_runtime()
        wsl = runtime is not None and runtime.kind == "wsl"
        script.write_text(
            pvpython_script(foam, case / "report.png", state, wsl=wsl),
            encoding="utf-8",
            newline="\n",
        )
        logger.info("Wrote %s; run it with pvpython to create %s", script, state)
        self.statusBar().showMessage(self.tr("ParaView state written"))

    def render_paraview(self) -> None:
        """Run pvpython_export.py through the saved runtime (pvpython must be on its PATH)."""
        from foamstudio.core.jobs import JobQueue
        from foamstudio.core.runtime import bind

        self.write_paraview_state()
        if self._project is None:
            return
        installation = self._store.load_runtime()
        if installation is None:
            logger.error("No runtime is saved.\n\nTools → Runtimes... and choose an installation.")
            return
        queue = JobQueue(bind(installation), self._project.case_dir)
        queue.add(
            "pvpython --force-offscreen-rendering pvpython_export.py > log.pvpython 2>&1"
            " || { tail -n 30 log.pvpython ; exit 1 ; }",
            name="pvpython",
        )
        case = self._project.case_dir

        def work() -> str:
            job = queue.run_blocking(live=True)[0]
            if job.status != "succeeded":
                raise RuntimeError(f"pvpython failed.\n{job.log_tail}\n\n{job.suggestion}")
            return f"Wrote {case / (case.name + '.pvsm')} and {case / 'report.png'}"

        self.statusBar().showMessage(self.tr("Running pvpython..."))
        self._render = _Background(work, self)
        self._render.ok.connect(self._render_done)
        self._render.failed.connect(lambda message: logger.error("%s", message))
        self._render.start()

    def _render_done(self, result: object) -> None:
        logger.info("%s", result)
        self.statusBar().showMessage(self.tr("ParaView export finished"))

    def _show_report_panel(self) -> None:
        if self._report_panel is None:
            self._report_panel = ReportPanel(self)
            self._report_panel.html_button.clicked.connect(
                lambda _checked=False: self.write_report(pdf=False)
            )
            self._report_panel.pdf_button.clicked.connect(
                lambda _checked=False: self.write_report(pdf=True)
            )
        self.properties_dock.setWidget(self._report_panel)

    def write_report(self, *, pdf: bool) -> None:
        from foamstudio.core.post.report import inputs_for_case, write_html

        if self._project is None:
            logger.error("Create or open a project before writing a report.")
            self.statusBar().showMessage(self.tr("Create or open a project"))
            return
        html_path = self._project.root / "report.html"
        try:
            report = inputs_for_case(self._project.root.name, self._project.case_dir)
            write_html(report, html_path)
        except OSError as exc:
            logger.error("%s", exc)
            self.statusBar().showMessage(self.tr("Report was not written"))
            return
        logger.info("Wrote %s", html_path)
        if pdf:
            from foamstudio.ui.report_panel import write_pdf

            pdf_path = self._project.root / "report.pdf"
            try:
                write_pdf(html_path.read_text(encoding="utf-8"), pdf_path)
            except OSError as exc:
                logger.error("%s", exc)
                return
            logger.info("Wrote %s", pdf_path)
        self.statusBar().showMessage(self.tr("Report written"))

    def open_dictionary(self) -> None:
        if self._dict_editor is None:
            self._dict_editor = DictEditor(self)
            self._dict_editor.preview.connect(self._preview_blocks)
        self.properties_dock.setWidget(self._dict_editor)
        if self._project is not None:
            self._dict_editor.load_case(self._project.case_dir)

    def _preview_blocks(self, text: str) -> None:
        from foamstudio.core.blockmesh_preview import parse_blockmesh

        try:
            points, hexes = parse_blockmesh(text)
        except ValueError as exc:
            self.statusBar().showMessage(f"Preview: {exc}")
            return
        self.statusBar().showMessage(self._view().show_blocks(points, hexes))

    def show_residuals(self, text: str) -> None:
        from foamstudio.core.logparse import parse_solver_log

        if self._residual_plot is None:
            self._residual_plot = ResidualPlot(self)
            self.console_tabs.removeTab(1)
            self.console_tabs.insertTab(1, self._residual_plot, self.tr("Residuals"))
        snapshot = parse_solver_log(text)
        self._residual_plot.set_samples(list(snapshot.residuals))
        if self._project is not None:
            from foamstudio.core.runinfo import coefficients

            self._residual_plot.set_coefficients(coefficients(self._project.case_dir))

    def raise_and_focus(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._writer is not None and self._writer.isRunning():
            self._writer.wait(3000)
        for worker in (self._solver, self._render):
            if worker is not None and worker.isRunning():
                worker.wait(3000)
        if self._log_handler is not None:
            logger.removeHandler(self._log_handler)
            self._log_handler = None
        super().closeEvent(event)

    def _step_font(self, delta: int, limit_message: str) -> None:
        size = self._model.font_point_size + delta
        if size < MIN_FONT_PT or size > MAX_FONT_PT:
            self.statusBar().showMessage(limit_message)
            return
        self._apply_model(replace(self._model, font_point_size=size), persist=True)

    def _project_runtime(self) -> Installation | None:
        """A runtime pinned to this project (.foamstudio/runtime.json) beats the global one,
        so one project can stay on Foundation 12 or a cluster while others use ESI."""
        if self._project is None:
            return None
        pinned = self._project.root / ".foamstudio" / "runtime.json"
        if not pinned.is_file():
            return None
        return Installation.from_dict(json.loads(pinned.read_text(encoding="utf-8")))

    def pin_runtime(self) -> Path | None:
        installation = self._store.load_runtime()
        if self._project is None or installation is None:
            self.statusBar().showMessage(self.tr("Open a project and pick a runtime first."))
            return None
        pinned = self._project.root / ".foamstudio" / "runtime.json"
        pinned.parent.mkdir(parents=True, exist_ok=True)
        pinned.write_text(json.dumps(installation.to_dict(), indent=1), encoding="utf-8")
        self.statusBar().showMessage(self.tr("Runtime pinned to this project"))
        return pinned

    # ---- hybrid dashboard (ui/web/dashboard.html over QWebChannel) ----
    def open_dashboard(self) -> QWidget | None:
        """Web dashboard as the centre view; None when WebEngine cannot load (headless)."""
        if os.environ.get("FOAMSTUDIO_HEADLESS") == "1":
            return None
        if self._dashboard is None:
            try:
                from foamstudio.ui.webpanel import WebPage

                self._dashboard = WebPage(self)
            except Exception as exc:
                logger.info("Web dashboard unavailable, keeping the native view: %s", exc)
                return None
        if self.centralWidget() is not self._dashboard:
            self.setCentralWidget(self._dashboard)
            self._dashboard.show()  # a widget taken out earlier stays hidden otherwise
            self._viewer3d = None  # setCentralWidget deleted the previous centre widget
        return self._dashboard

    def _set_centre(self, widget: QWidget) -> None:
        """Swap the centre view without deleting the dashboard (setCentralWidget would)."""
        if self._dashboard is not None and self.centralWidget() is self._dashboard:
            self.takeCentralWidget()
        self.setCentralWidget(widget)
        widget.show()

    def dashboard_state(self) -> dict[str, object]:
        from foamstudio.core import licence, runinfo, workspace
        from foamstudio.core.logparse import parse_solver_log
        from foamstudio.ui.webpanel import series

        state: dict[str, object] = {
            "theme": self._model.theme,
            "project": None,
            "path": "",
            "running": bool(self._solver is not None and self._solver.isRunning())
            or self._background_alive(),
            "cores": runinfo.physical_cores(),
            "ram": workspace.total_memory_gb(),
            "licence": licence.status()[1],
            "wsl": "WSL "
            + ", ".join(
                f"{k} {v}"
                for k, v in workspace.read_wslconfig().items()
                if k in ("memory", "processors")
            ),
            "processes": self._run_panel.processes.value() if self._run_panel else 1,
            "detached": bool(self._run_panel and self._run_panel.detached.isChecked()),
            "cells": 0,
            "memory": 0.0,
            "suggested": 1,
            "progress": None,
            "monitor": {},
            "residuals": {},
            "coefficients": {},
            "history": [],
        }
        runtime = self._store.load_runtime()
        state["runtime"] = runtime.label() if runtime is not None else None
        if self._project is None:
            return state
        case = self._project.case_dir
        cells = runinfo.cell_count(case)
        state.update(
            project=self._project.root.name,
            path=str(self._project.root),
            cells=cells,
            memory=runinfo.memory_gb(cells),
            suggested=runinfo.suggest_processes(cells) if cells else 1,
            history=workspace.load_history(case)[::-1][:8],
        )
        logs = sorted(
            [*case.glob("log.*Foam"), *case.glob("log.foamRun")], key=lambda p: p.stat().st_mtime
        )
        if logs:
            text = logs[-1].read_text(encoding="utf-8", errors="replace")
            by_field: dict[str, tuple[list[float], list[float]]] = {}
            for sample in parse_solver_log(text).residuals:
                xs, ys = by_field.setdefault(sample.field, ([], []))
                xs.append(sample.time)
                ys.append(sample.initial)
            state["residuals"] = {f: series(*v) for f, v in by_field.items()}
            p = runinfo.progress(text, _end_time(case))
            if p is not None:
                state["progress"] = {"t": p.iteration, "rate": p.per_second, "eta": p.eta_seconds}
            state["monitor"] = workspace.monitor(text)
        coeffs = runinfo.coefficients(case)
        if coeffs.get("Time"):
            state["coefficients"] = {
                n: series(coeffs["Time"], coeffs[n]) for n in ("Cd", "Cl") if coeffs.get(n)
            }
        return state

    def _background_alive(self) -> bool:
        from foamstudio.core.runtime.paths import DETACHED

        if self._project is None or not (self._project.case_dir / DETACHED).is_file():
            return False
        logs = list(self._project.case_dir.glob("log.*"))
        return bool(logs) and time.time() - max(p.stat().st_mtime for p in logs) < 30

    def dashboard_action(self, name: str, arg: str) -> None:
        """Buttons on the web page. Anything that needs a dialog or the 3D view stays native."""
        if name in ("processes", "detached", "continue"):
            self._show_run_panel()
        panel = self._run_panel
        actions = {
            "run": lambda: self.start_solver(),
            "stop": self.stop_solver,
            "continue": lambda: (panel.end_time.setText(arg), self.start_solver(resume=True)),
            "processes": lambda: panel.processes.setValue(max(1, int(arg or 1))),
            "detached": lambda: panel.detached.setChecked(bool(arg)),
            "new": self.new_project_dialog,
            "open": self.open_project_dialog,
            "airfoil": self.new_airfoil_dialog,
            "demo": self.run_demo,
            "setup": self.open_setup,
            "tools": self.open_tools,
            "mesh": self.show_mesh,
            "field": lambda: self.show_field(arg or "p"),
            "quality": self.show_mesh_quality,
            "report": lambda: self.write_report(pdf=False),
            "dict": self.open_dictionary,
            "install": self.open_install_setup,
            "runtimes": lambda: self.open_install_setup(tab=1),
            "ssh": lambda: self.open_install_setup(tab=2),
            "palette": self.open_palette,
            "console": self.open_console,
            "vscode": self.open_vscode,
            "problem": self.report_problem,
            "physics": self.open_physics,
        }
        action = actions.get(name)
        if action is None:
            logger.error("Unknown dashboard action %r", name)
            return
        try:
            action()
        except Exception as exc:
            logger.error("%s", exc)
            self.statusBar().showMessage(str(exc).splitlines()[0])

    # ---- workspace tools host API (ToolsPanel calls these) ----
    def open_tools(self) -> ToolsPanel:
        if self._tools is None:
            self._tools = ToolsPanel(self)
        self._tools.refresh()
        self.properties_dock.setWidget(self._tools)
        self.properties_dock.show()
        return self._tools

    def run_command(self, command: str, name: str) -> None:
        self.start_solver(commands=[(command, name.replace(".", "_"))])

    def remesh(self) -> None:
        if self._project is None:
            return
        steps = [("blockMesh", "blockMesh")]
        if (self._project.case_dir / "system" / "snappyHexMeshDict").is_file():
            steps += [
                ("surfaceFeatureExtract", "surfaceFeatureExtract"),
                ("snappyHexMesh -overwrite", "snappyHexMesh"),
            ]
        self.start_solver(commands=[*steps, ("checkMesh", "checkMesh")])

    def _view(self) -> Viewer3D:
        if self._viewer3d is None:
            self._viewer3d = Viewer3D(self)
            self._set_centre(self._viewer3d)
        return self._viewer3d

    def show_mesh(self) -> str:
        if self._project is None:
            return ""
        return self._view().show_case(self._project.case_dir, None)

    def show_field(self, field: str) -> str:
        if self._project is None:
            return ""
        return self._view().show_case(self._project.case_dir, field or None)

    def show_streamlines(self) -> str:
        return "" if self._project is None else self._view().streamlines(self._project.case_dir)

    def animate_field(self, field: str) -> str:
        return "" if self._project is None else self._view().animate(self._project.case_dir, field)

    def line_plot(self, field: str, a: tuple[float, ...], b: tuple[float, ...]) -> Path | None:
        """Probe along a-b: plot in a dialog and write <case>/line_<field>.csv."""
        if self._project is None:
            return None
        from foamstudio.core.workspace import export_csv

        try:
            distance, values = self._view().line_values(self._project.case_dir, field, a, b)
        except Exception as exc:
            logger.error("Line plot failed: %s", exc)
            self.statusBar().showMessage(f"Line plot failed: {exc}")
            return None
        path = export_csv(
            {"distance": distance, field: values}, self._project.case_dir / f"line_{field}.csv"
        )
        try:
            import pyqtgraph as pg
            from PySide6.QtWidgets import QDialog, QVBoxLayout

            dialog = QDialog(self)
            dialog.setWindowTitle(f"{field} along the line")
            plot = pg.PlotWidget()
            plot.plot(distance, values)
            plot.setLabel("bottom", "distance")
            plot.setLabel("left", field)
            QVBoxLayout(dialog).addWidget(plot)
            dialog.resize(700, 450)
            dialog.show()
        except Exception as exc:
            logger.info("Line plot window skipped: %s", exc)
        self.statusBar().showMessage(self.tr("Line data written to %1").replace("%1", str(path)))
        return path

    def run_demo(self) -> Project | None:
        """Lid-driven cavity in ~/FoamStudio/demo-cavity, then run it."""
        from foamstudio.core.workspace import templates

        spec = templates().get("cavity/case")
        if spec is None:
            self.statusBar().showMessage(self.tr("The cavity sample is not installed."))
            return None
        root = Path.home() / "FoamStudio" / f"demo-cavity-{time.strftime('%Y%m%d-%H%M%S')}"
        project = self.create_from_spec(root, spec)
        if project is not None:
            self._show_run_panel()
            if self._run_panel is not None:
                self._run_panel.processes.setValue(1)  # 4k cells: serial is fastest
            self.start_solver()
        return project

    def save_plots(self) -> list[Path]:
        plot = self._residual_plot
        if self._project is None or plot is None:
            self.statusBar().showMessage(self.tr("No plots yet: run the case first."))
            return []
        out = []
        for widget, name in (
            (plot._plot, "residuals.png"),
            (plot._coeff_plot, "coefficients.png"),
        ):
            if widget is not None:
                path = self._project.case_dir / name
                widget.grab().save(str(path))
                out.append(path)
        self.statusBar().showMessage(self.tr("Saved %1 plots").replace("%1", str(len(out))))
        return out

    def show_text(self, title: str, text: str) -> None:
        from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        view = QPlainTextEdit(text)
        view.setReadOnly(True)
        QVBoxLayout(dialog).addWidget(view)
        dialog.resize(900, 600)
        dialog.show()

    def create_from_spec(self, root: Path, spec: Path) -> Project | None:
        from foamstudio.generator.write_case import write_spec_file

        project = self.create_project(root)
        if project is None:
            return None
        try:
            write_spec_file(project, spec, app_version=__version__)
            # case-axi.json -> blockMeshDict-axi, case.json -> blockMeshDict
            variant = spec.parent / f"blockMeshDict{spec.stem.removeprefix('case')}"
            mesh = variant if variant.is_file() else spec.parent / "blockMeshDict"
            if mesh.is_file():
                (project.case_dir / "system" / "blockMeshDict").write_bytes(mesh.read_bytes())
        except Exception as exc:
            logger.error("%s", exc)
            return None
        self.statusBar().showMessage(self.tr("Case written from %1").replace("%1", spec.name))
        return project

    def run_sweep(self, folder: Path, alphas: list[float], code: str = "0012") -> list[Path]:
        """One airfoil project per angle, then their Allruns in sequence as one queue."""
        from foamstudio.core.project import create_project as make
        from foamstudio.generator.write_case import write_airfoil

        cases = []
        for alpha in alphas:
            project = make(folder / f"naca{code}_a{alpha:g}", app_version=__version__)
            write_airfoil(project, code, alpha, 6e6, app_version=__version__)
            cases.append(project.case_dir)
        steps = [(f"bash ./{c.parent.name}/case/Allrun", f"Allrun_{c.parent.name}") for c in cases]
        self.start_solver(commands=steps, workdir=folder)
        return cases

    def enter_licence_dialog(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        from foamstudio.core.licence import LicenceError, save_key

        key, ok = QInputDialog.getText(self, self.tr("Licence"), self.tr("Licence key"))
        if not ok or not key.strip():
            return
        try:
            lic = save_key(key)
        except (LicenceError, OSError, KeyError) as exc:
            logger.error("%s", exc)
            self.statusBar().showMessage(str(exc))
            return
        self.statusBar().showMessage(self.tr("Licensed to %1").replace("%1", lic.email))

    def _about(self) -> None:
        QMessageBox.about(
            self,
            self.tr("FoamStudio"),
            "\n".join(
                [
                    f"FoamStudio {__version__}",
                    "Copyright (C) 2026 Shanthosh K V",
                    APP_LICENSE,
                    "",
                    "There is no warranty. See the GNU General Public License version 3.",
                    "",
                    "OpenFOAM is not bundled. It runs as an external process.",
                ]
            ),
        )
