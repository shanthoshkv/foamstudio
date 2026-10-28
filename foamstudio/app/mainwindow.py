"""Dock shell: project tree, viewer, properties, console."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
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
from foamstudio.app.theme import load_icon, load_qss, mono_font
from foamstudio.core.project import Project, ProjectError
from foamstudio.core.project import create_project as create_project_at
from foamstudio.core.project import open_project as open_project_at
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
from foamstudio.ui.runtime_wizard import RuntimeWizard
from foamstudio.ui.setup_panel import SetupPanel
from foamstudio.ui.viewer3d import Viewer3D

logger = logging.getLogger("foamstudio")

_SECTIONS = ("Geometry", "Mesh", "Setup", "Run", "Results", "Reports")
_CONSOLE_TABS = (
    ("Log", ""),
    ("Residuals", "No residuals yet."),
    ("Monitors", "No monitors yet."),
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
        self._jobs = None
        self._solver: _Background | None = None
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

        tools_menu = self.menuBar().addMenu(self.tr("Tools"))
        runtimes = QAction(self.tr("Runtimes..."), self)
        runtimes.setObjectName("actionRuntimes")
        runtimes.triggered.connect(lambda _checked=False: self.open_runtime_wizard())
        dictionary = QAction(self.tr("Dictionary editor..."), self)
        dictionary.setObjectName("actionDictionary")
        dictionary.triggered.connect(lambda _checked=False: self.open_dictionary())
        tools_menu.addAction(runtimes)
        tools_menu.addAction(dictionary)

        help_menu = self.menuBar().addMenu(self.tr("Help"))
        about = QAction(self.tr("About"), self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _theme_action(self, label: str, theme: str) -> QAction:
        action = QAction(label, self)
        action.setCheckable(True)
        action.setData(theme)
        action.triggered.connect(lambda: self.set_theme(theme))
        self._theme_group.addAction(action)
        return action

    def _attach_log_handler(self) -> None:
        bridge = _LogBridge(self)
        bridge.message.connect(self.log_view.appendPlainText)
        handler = _QtLogHandler(bridge)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        self._log_handler = handler

    def _apply_model(self, model: SettingsModel, *, persist: bool) -> None:
        model.validate()
        self._model = model
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(load_qss(model.theme))
            app.setFont(mono_font(model.font_point_size))
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
        folder = QFileDialog.getExistingDirectory(self, self.tr("New project folder"))
        if folder:
            self.create_project(Path(folder))

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

    def open_runtime_wizard(self) -> None:
        dialog = RuntimeWizard(self._store, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage(self.tr("Runtime saved"))

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
        self.setCentralWidget(view)
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
        self.properties_dock.setWidget(self._mesh_panel)

    def write_block_mesh(self) -> None:
        from foamstudio.core.mesh import MeshFailure, block_mesh_dict

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
            text = block_mesh_dict(kind)
        except MeshFailure as exc:
            logger.error("%s", exc)
            return
        target = self._project.case_dir / "system" / "blockMeshDict"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        logger.info("Wrote %s", target)
        self.statusBar().showMessage(self.tr("blockMeshDict written"))

    def _show_run_panel(self) -> None:
        if self._run_panel is None:
            self._run_panel = RunPanel(self)
            self._run_panel.start_button.clicked.connect(lambda _checked=False: self.start_solver())
            self._run_panel.stop_button.clicked.connect(lambda _checked=False: self.stop_solver())
        self.properties_dock.setWidget(self._run_panel)

    def start_solver(self) -> None:
        from foamstudio.core.jobs import JobQueue
        from foamstudio.core.runtime import bind

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
        installation = self._store.load_runtime()
        if installation is None:
            logger.error("No runtime is saved.\n\nTools → Runtimes... and choose an installation.")
            self.statusBar().showMessage(self.tr("No runtime is saved"))
            return
        solver = self._run_panel.solver.text().strip() or "simpleFoam"
        queue = JobQueue(bind(installation), self._project.case_dir)
        queue.add_allrun(solver, parallel=self._run_panel.processes.value())
        self._jobs = queue
        logger.info("Running %s", ", ".join(job.command for job in queue.jobs))

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
            return "\n".join(f"{job.status} {job.command}" for job in results)

        self.statusBar().showMessage(self.tr("Running"))
        self._solver = _Background(work, self)
        self._solver.ok.connect(self._solver_ok)
        self._solver.failed.connect(self._solver_fail)
        self._solver.start()

    def stop_solver(self) -> None:
        queue = self._jobs
        if queue is None:
            logger.error("There is no solver job to stop.\n\nRun the case before using Stop.")
            return
        argv = queue.cancel()
        if argv is not None:
            subprocess.run(list(argv), check=False)
            logger.info("Kill %s", " ".join(argv))
        self.statusBar().showMessage(self.tr("Stop requested"))

    def _solver_ok(self, result: object) -> None:
        logger.info("%s", result)
        self.statusBar().showMessage(self.tr("Run finished"))

    def _solver_fail(self, message: str) -> None:
        logger.error("%s", message)
        self.statusBar().showMessage(self.tr("Run failed"))

    def _show_post_panel(self) -> None:
        if self._post_panel is None:
            self._post_panel = PostPanel(self)
            self._post_panel.export_button.clicked.connect(
                lambda _checked=False: self.write_paraview_state()
            )
        self.properties_dock.setWidget(self._post_panel)

    def write_paraview_state(self) -> None:
        from foamstudio.core.post.paraview import (
            ParaViewFailure,
            pvpython_script,
            write_foam,
            write_state,
        )

        if self._project is None:
            logger.error("Create or open a project before writing a ParaView state.")
            self.statusBar().showMessage(self.tr("Create or open a project"))
            return
        case = self._project.case_dir
        try:
            foam = write_foam(case)
            state = write_state(foam, case / f"{case.name}.pvsm")
        except ParaViewFailure as exc:
            logger.error("%s", exc)
            return
        script = case / "pvpython_export.py"
        script.write_text(
            pvpython_script(foam, case / "report.png"), encoding="utf-8", newline="\n"
        )
        logger.info("Wrote %s and %s", state, script)
        self.statusBar().showMessage(self.tr("ParaView state written"))

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
        self.properties_dock.setWidget(self._dict_editor)

    def show_residuals(self, text: str) -> None:
        from foamstudio.core.logparse import parse_solver_log

        if self._residual_plot is None:
            self._residual_plot = ResidualPlot(self)
            self.console_tabs.removeTab(1)
            self.console_tabs.insertTab(1, self._residual_plot, self.tr("Residuals"))
        snapshot = parse_solver_log(text)
        self._residual_plot.set_samples(list(snapshot.residuals))

    def raise_and_focus(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._writer is not None and self._writer.isRunning():
            self._writer.wait(3000)
        if self._solver is not None and self._solver.isRunning():
            self._solver.wait(3000)
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
