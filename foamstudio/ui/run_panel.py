"""Run controls. The job itself runs on a worker thread owned by the main window."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class RunPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("runPanel")
        self.solver = QLineEdit("simpleFoam")
        self.solver.setObjectName("solverName")
        self.processes = QSpinBox()
        self.processes.setObjectName("processCount")
        self.processes.setRange(1, 256)
        self.processes.setValue(1)
        self.start_button = QPushButton(self.tr("Run"))
        self.start_button.setObjectName("runButton")
        self.stop_button = QPushButton(self.tr("Stop"))
        self.stop_button.setObjectName("stopButton")
        self.note = QLabel(
            self.tr("Each Allrun step is a tracked job. Stop kills the process tree.")
        )
        self.note.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Solver")))
        layout.addWidget(self.solver)
        layout.addWidget(QLabel(self.tr("Processes")))
        layout.addWidget(self.processes)
        layout.addLayout(buttons)
        layout.addWidget(self.note)
        layout.addStretch(1)
