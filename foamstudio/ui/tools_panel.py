"""Workspace tools dock: Resources, Files, Scripts, Mesh, Results, Runs.

The panel holds widgets and calls back into the main window (`host`) for anything that
runs a job, touches the viewer or changes the project. Logic lives in core/workspace.py.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDir
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFileSystemModel,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from foamstudio.core import workspace as ws


def _button(text: str, name: str, slot: Any) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.clicked.connect(lambda _checked=False: slot())
    return button


def _fill(table: QTableWidget, rows: list[list[str]], headers: list[str]) -> None:
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(value))
    table.resizeColumnsToContents()


class ToolsPanel(QTabWidget):
    def __init__(self, host: Any) -> None:
        super().__init__(host)
        self.setObjectName("toolsPanel")
        self.host = host
        self.addTab(self._resources(), self.tr("Resources"))
        self.addTab(self._files(), self.tr("Files"))
        self.addTab(self._scripts(), self.tr("Scripts"))
        self.addTab(self._mesh(), self.tr("Mesh"))
        self.addTab(self._results(), self.tr("Results"))
        self.addTab(self._runs(), self.tr("Runs"))
        self.refresh()

    # ------------------------------------------------------------ helpers
    def case(self) -> Path | None:
        project = getattr(self.host, "_project", None)
        return None if project is None else Path(project.case_dir)

    def say(self, text: str) -> None:
        self.host.statusBar().showMessage(text.splitlines()[0] if text else "")

    # ------------------------------------------------------------ resources
    def _resources(self) -> QWidget:
        page = QWidget()
        self.machine = QLabel()
        self.machine.setObjectName("machineInfo")
        self.machine.setWordWrap(True)
        self.mem = QSpinBox()
        self.mem.setObjectName("wslMemory")
        self.mem.setSuffix(" GB")
        self.cpus = QSpinBox()
        self.cpus.setObjectName("wslProcessors")
        self.swap = QSpinBox()
        self.swap.setObjectName("wslSwap")
        self.swap.setSuffix(" GB")
        self.swap.setRange(0, 64)
        self.usage = QPlainTextEdit()
        self.usage.setReadOnly(True)
        self.usage.setMaximumHeight(90)
        self.licence = QLabel()
        self.licence.setObjectName("licenceStatus")
        self.licence.setWordWrap(True)
        form = QFormLayout()
        form.addRow(self.tr("WSL memory"), self.mem)
        form.addRow(self.tr("WSL processors"), self.cpus)
        form.addRow(self.tr("WSL swap"), self.swap)
        layout = QVBoxLayout(page)
        layout.addWidget(self.machine)
        layout.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(_button(self.tr("Apply (restarts WSL)"), "applyWsl", self.apply_wsl))
        row.addWidget(_button(self.tr("WSL usage"), "wslUsage", self.show_usage))
        row.addWidget(_button(self.tr("Shut down WSL"), "wslShutdown", self.shutdown_wsl))
        layout.addLayout(row)
        layout.addWidget(self.usage)
        layout.addWidget(self.licence)
        layout.addWidget(_button(self.tr("Check for updates"), "checkUpdates", self.updates))
        layout.addStretch(1)
        return page

    def refresh(self) -> None:
        from foamstudio.core.licence import status
        from foamstudio.core.runinfo import physical_cores

        total = ws.total_memory_gb()
        cfg = ws.read_wslconfig()
        cap = max(1, int(total * ws.MAX_WSL_FRACTION))
        self.mem.setRange(1, cap)
        self.cpus.setRange(1, os.cpu_count() or 1)
        self.mem.setValue(int(cfg.get("memory", f"{total / 2:.0f}GB").rstrip("GBgb") or 1))
        self.cpus.setValue(int(cfg.get("processors", str(os.cpu_count() or 1))))
        self.swap.setValue(int(cfg.get("swap", "0GB").rstrip("GBgb") or 0))
        self.machine.setText(
            self.tr("This machine: %1 GB RAM, %2 logical / %3 physical cores. WSL cap %4 GB.")
            .replace("%1", f"{total:.1f}")
            .replace("%2", str(os.cpu_count()))
            .replace("%3", str(physical_cores()))
            .replace("%4", str(cap))
        )
        self.licence.setText(status()[1])
        self.refresh_case()

    def apply_wsl(self) -> None:
        running = getattr(self.host, "_solver", None)
        if running is not None and running.isRunning():
            QMessageBox.warning(self, "WSL", self.tr("Stop the running solver first."))
            return
        try:
            path = ws.write_wslconfig(self.mem.value(), self.cpus.value(), self.swap.value())
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "WSL", str(exc))
            return
        subprocess.run(list(ws.wsl_shutdown_argv()), check=False)
        self.say(self.tr("Wrote %1 and restarted WSL").replace("%1", str(path)))

    def show_usage(self) -> None:
        self.usage.setPlainText(ws.wsl_usage())

    def shutdown_wsl(self) -> None:
        subprocess.run(list(ws.wsl_shutdown_argv()), check=False)
        self.say(self.tr("WSL shut down"))

    def updates(self) -> None:
        from foamstudio import __version__

        try:
            self.say(ws.check_update(__version__))
        except Exception as exc:
            self.say(f"Update check failed: {exc}")

    # ------------------------------------------------------------ files
    def _files(self) -> QWidget:
        page = QWidget()
        self.roots = QComboBox()
        self.roots.setObjectName("fileRoot")
        self.roots.addItem(self.tr("This PC"), "")
        self.roots.addItem(self.tr("Home"), str(Path.home()))
        for distro in ws.list_distros():
            self.roots.addItem(f"WSL {distro}", rf"\\wsl.localhost\{distro}")
        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        self.model.setRootPath("")
        self.tree = QTreeView()
        self.tree.setObjectName("fileTree")
        self.tree.setModel(self.model)
        for column in (1, 2, 3):
            self.tree.hideColumn(column)
        self.roots.currentIndexChanged.connect(self._root_changed)
        layout = QVBoxLayout(page)
        layout.addWidget(self.roots)
        layout.addWidget(self.tree, 1)
        layout.addWidget(
            _button(
                self.tr("Import selected into this case"), "importSelected", self.import_selected
            )
        )
        layout.addWidget(
            _button(self.tr("New case from selected folder..."), "newCaseFrom", self.new_case_from)
        )
        return page

    def _root_changed(self) -> None:
        root = str(self.roots.currentData() or "")
        self.tree.setRootIndex(self.model.index(root) if root else self.model.index(""))

    def selected_path(self) -> Path | None:
        index = self.tree.currentIndex()
        return Path(self.model.filePath(index)) if index.isValid() else None

    def import_path(self, src: Path, case: Path) -> str:
        kind, copied = ws.import_into(src, case)
        text = f"Imported {src.name} as {kind}: {len(copied)} files into {case}"
        self.say(text)
        self.refresh_case()
        return text

    def import_selected(self) -> None:
        src, case = self.selected_path(), self.case()
        if src is None or case is None:
            self.say(self.tr("Select a file or folder and open a project first."))
            return
        self.import_path(src, case)

    def new_case_from(self) -> None:
        src = self.selected_path()
        if src is None:
            self.say(self.tr("Select a folder in the tree first."))
            return
        start = next(
            (
                r
                for r in (self.roots.itemData(i) for i in range(self.roots.count()))
                if r and "wsl" in r
            ),
            "",
        )
        dest = QFileDialog.getExistingDirectory(
            self, self.tr("Parent folder for the new case"), start
        )
        if not dest:
            return
        name, ok = QInputDialog.getText(
            self, self.tr("New case"), self.tr("Folder name"), text=src.name
        )
        if ok and name.strip():
            self.new_case(src, Path(dest) / name.strip())

    def new_case(self, src: Path, root: Path) -> Path | None:
        project = self.host.create_project(root)
        if project is None:
            return None
        self.import_path(src, Path(project.case_dir))
        return Path(project.case_dir)

    # ------------------------------------------------------------ scripts
    def _scripts(self) -> QWidget:
        page = QWidget()
        self.script_list = QListWidget()
        self.script_list.setObjectName("scriptList")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(self.tr("Scripts in the case folder (Allrun*, *.sh, *.py)")))
        layout.addWidget(self.script_list, 1)
        row = QHBoxLayout()
        row.addWidget(_button(self.tr("Import folder..."), "importFolder", self.import_folder))
        row.addWidget(_button(self.tr("Import files..."), "importFiles", self.import_files))
        row.addWidget(_button(self.tr("Run selected"), "runScript", self.run_script))
        layout.addLayout(row)
        return page

    def import_folder(self) -> None:
        case = self.case()
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("Case, 0/constant/system or scripts folder")
        )
        if folder and case is not None:
            self.import_path(Path(folder), case)

    def import_files(self) -> None:
        case = self.case()
        files, _ = QFileDialog.getOpenFileNames(self, self.tr("Scripts or case files"))
        for name in files if case is not None else []:
            self.import_path(Path(name), case)  # type: ignore[arg-type]

    def run_script(self) -> None:
        item = self.script_list.currentItem()
        case = self.case()
        if item is None or case is None:
            self.say(self.tr("Select a script first."))
            return
        try:
            command = ws.script_command(case / item.text())
            ws.fix_text(case / item.text())  # a script saved by a Windows editor has CRLF
        except ValueError as exc:
            self.say(str(exc))
            return
        self.host.run_command(command, item.text())

    # ------------------------------------------------------------ mesh
    def _mesh(self) -> QWidget:
        page = QWidget()
        self.checks = QTableWidget()
        self.checks.setObjectName("checkTable")
        self.patches = QTableWidget()
        self.patches.setObjectName("boundaryTable")
        self.u = QDoubleSpinBox()
        self.u.setRange(1e-3, 1e4)
        self.u.setValue(10)
        self.length = QDoubleSpinBox()
        self.length.setRange(1e-4, 1e3)
        self.length.setDecimals(4)
        self.length.setValue(1)
        self.nu = QLineEdit("1.5e-5")
        self.yplus = QDoubleSpinBox()
        self.yplus.setRange(0.1, 500)
        self.yplus.setValue(1)
        self.first = QLabel()
        self.first.setObjectName("firstCell")
        form = QFormLayout()
        form.addRow(self.tr("Velocity (m/s)"), self.u)
        form.addRow(self.tr("Length (m)"), self.length)
        form.addRow(self.tr("ν (m²/s)"), self.nu)
        form.addRow(self.tr("Target y+"), self.yplus)
        form.addRow(self.tr("First cell height"), self.first)
        for w in (self.u, self.length, self.yplus):
            w.valueChanged.connect(lambda _v: self.plan_yplus())
        self.nu.textChanged.connect(lambda _t: self.plan_yplus())
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(_button(self.tr("View mesh"), "viewMesh", lambda: self.host.show_mesh()))
        row.addWidget(_button(self.tr("Re-mesh"), "remesh", lambda: self.host.remesh()))
        row.addWidget(
            _button(self.tr("Worst cells"), "worstCells", lambda: self.host.show_mesh_quality())
        )
        layout.addLayout(row)
        layout.addWidget(QLabel(self.tr("checkMesh (log.checkMesh)")))
        layout.addWidget(self.checks, 1)
        layout.addWidget(QLabel(self.tr("Patches: edit Name or Type, then Apply")))
        layout.addWidget(self.patches, 1)
        layout.addWidget(_button(self.tr("Apply patch edits"), "applyPatches", self.apply_patches))
        layout.addWidget(QLabel(self.tr("y+ planner")))
        layout.addLayout(form)
        self.plan_yplus()
        return page

    def plan_yplus(self) -> None:
        from foamstudio.core.mesh import MeshFailure, first_cell_height

        try:
            h = first_cell_height(
                self.u.value(), float(self.nu.text()), self.length.value(), self.yplus.value()
            )
        except (ValueError, MeshFailure) as exc:
            self.first.setText(str(exc).splitlines()[0])
            return
        self.first.setText(f"{h:.3g} m")

    def apply_patches(self) -> None:
        case = self.case()
        if case is None:
            return
        old = ws.boundary_patches(case)
        try:
            for row, (name, kind, _faces) in enumerate(old):
                new_name = self.patches.item(row, 0).text().strip()
                new_kind = self.patches.item(row, 1).text().strip()
                if (new_name, new_kind) != (name, kind):
                    ws.edit_boundary(case, name, new_name=new_name, new_type=new_kind)
        except (ValueError, OSError, AttributeError) as exc:
            self.say(str(exc))
            return
        self.say(
            self.tr(
                "polyMesh/boundary updated. Rename the same patches in 0/ (or rewrite the case)."
            )
        )
        self.refresh_case()

    # ------------------------------------------------------------ results
    def _results(self) -> QWidget:
        page = QWidget()
        self.field = QComboBox()
        self.field.setObjectName("fieldChoice")
        self.field.setEditable(True)
        self.field.addItems(["p", "U", "k", "nut", "nuTilda", "omega", "T"])
        self.monitor_text = QLabel()
        self.monitor_text.setObjectName("monitorText")
        self.monitor_text.setWordWrap(True)
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(self.field)
        row.addWidget(
            _button(
                self.tr("Colour by field"),
                "colourField",
                lambda: self.host.show_field(self.field.currentText()),
            )
        )
        layout.addLayout(row)
        layout.addWidget(
            _button(self.tr("Export residuals + Cd/Cl CSV..."), "exportCsv", self.export)
        )
        layout.addWidget(
            _button(self.tr("Save plots as PNG..."), "savePng", lambda: self.host.save_plots())
        )
        layout.addWidget(QLabel(self.tr("Solver monitor")))
        layout.addWidget(self.monitor_text)
        layout.addStretch(1)
        return page

    def export(self) -> list[Path]:

        case = self.case()
        if case is None:
            return []
        folder = QFileDialog.getExistingDirectory(self, self.tr("Export folder"), str(case))
        if not folder:
            return []
        return self.export_to(Path(folder))

    def export_to(self, folder: Path) -> list[Path]:
        from foamstudio.core.runinfo import coefficients

        case = self.case()
        assert case is not None
        out = []
        logs = sorted(case.glob("log.*Foam")) + sorted(case.glob("log.foamRun"))
        if logs:
            text = logs[0].read_text(encoding="utf-8", errors="replace")
            out.append(ws.export_csv(ws.residual_columns(text), folder / "residuals.csv"))
        coeffs = coefficients(case)
        if coeffs:
            out.append(ws.export_csv(coeffs, folder / "coefficients.csv"))
        self.say(f"Exported {len(out)} CSV files to {folder}")
        return out

    def set_monitor(self, log_text: str) -> None:
        values = ws.monitor(log_text)
        self.monitor_text.setText("  ".join(f"{k} {v:.3g}" for k, v in values.items()))

    # ------------------------------------------------------------ runs
    def _runs(self) -> QWidget:
        page = QWidget()
        self.history = QTableWidget()
        self.history.setObjectName("historyTable")
        self.disk = QLabel()
        self.disk.setObjectName("diskUsage")
        self.disk.setWordWrap(True)
        self.template = QComboBox()
        self.template.setObjectName("templateChoice")
        for name, path in ws.templates().items():
            self.template.addItem(name, str(path))
        self.sweep_values = QLineEdit("0, 2, 4, 6, 8, 10")
        self.sweep_values.setObjectName("sweepValues")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(self.tr("Run history")))
        layout.addWidget(self.history, 1)
        layout.addWidget(
            _button(self.tr("Compare with another case..."), "compareCase", self.compare)
        )
        row = QHBoxLayout()
        row.addWidget(self.template, 1)
        row.addWidget(_button(self.tr("New from template..."), "newTemplate", self.new_template))
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Airfoil α sweep")))
        row.addWidget(self.sweep_values, 1)
        row.addWidget(_button(self.tr("Create + run..."), "runSweep", self.sweep))
        layout.addLayout(row)
        layout.addWidget(self.disk)
        row = QHBoxLayout()
        row.addWidget(
            _button(self.tr("Delete processor*"), "cleanProcs", lambda: self.clean(True, False))
        )
        row.addWidget(
            _button(self.tr("Keep latest time only"), "cleanTimes", lambda: self.clean(False, True))
        )
        layout.addLayout(row)
        layout.addWidget(
            _button(
                self.tr("Pin current runtime to this project (version / SSH / cluster)"),
                "pinRuntime",
                lambda: self.host.pin_runtime(),
            )
        )
        return page

    def refresh_case(self) -> None:
        case = self.case()
        if case is None:
            return
        self.script_list.clear()
        self.script_list.addItems([p.name for p in ws.scripts_in(case)])
        log = case / "log.checkMesh"
        rows = (
            ws.check_table(log.read_text(encoding="utf-8", errors="replace"))
            if log.is_file()
            else []
        )
        _fill(
            self.checks,
            [[r.name, r.value, r.limit, "OK" if r.ok else "FAIL"] for r in rows],
            ["Check", "Value", "Limit", ""],
        )
        _fill(
            self.patches,
            [[n, t, str(f)] for n, t, f in ws.boundary_patches(case)],
            ["Name", "Type", "Faces"],
        )
        history = ws.load_history(case)
        _fill(
            self.history,
            [
                [str(h.get(k, "")) for k in ("started", "name", "status", "seconds")]
                for h in history[::-1]
            ],
            ["Started", "Run", "Status", "s"],
        )
        usage = ws.disk_usage(case)
        self.disk.setText("  ".join(f"{k}: {v / 2**20:.1f} MB" for k, v in usage.items()))

    def compare(self) -> None:
        case = self.case()
        other = QFileDialog.getExistingDirectory(self, self.tr("Case to compare with"))
        if case is None or not other:
            return
        other_case = Path(other) / "case" if (Path(other) / "case").is_dir() else Path(other)
        self.host.show_text(self.tr("Compare"), ws.compare_cases(case, other_case))

    def new_template(self) -> None:
        spec = self.template.currentData()
        folder = QFileDialog.getExistingDirectory(self, self.tr("New project folder"))
        if spec and folder:
            self.host.create_from_spec(Path(folder), Path(spec))

    def sweep(self) -> None:
        try:
            values = [
                float(v) for v in self.sweep_values.text().replace(";", ",").split(",") if v.strip()
            ]
        except ValueError:
            self.say(self.tr("Sweep values must be numbers separated by commas."))
            return
        folder = QFileDialog.getExistingDirectory(self, self.tr("Folder for the sweep cases"))
        if folder and values:
            self.host.run_sweep(Path(folder), values)

    def clean(self, processors: bool, keep_latest: bool) -> None:
        case = self.case()
        if case is None:
            return
        removed = ws.clean(case, processors=processors, keep_latest=keep_latest)
        self.say(f"Removed {len(removed)} folders")
        self.refresh_case()
