"""blockMesh kind picker. The dictionary is built in core.mesh."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget


class MeshPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("meshPanel")
        self.kind = QComboBox()
        self.kind.setObjectName("meshKind")
        self.kind.addItems(["box", "channel", "wedge"])
        self.note = QLabel(
            self.tr("Writes system/blockMeshDict. Solver dictionaries stay in the generator.")
        )
        self.note.setWordWrap(True)
        self.write_button = QPushButton(self.tr("Write blockMeshDict"))
        self.write_button.setObjectName("writeBlockMesh")
        layout = QVBoxLayout(self)
        layout.addWidget(self.kind)
        layout.addWidget(self.note)
        layout.addWidget(self.write_button)
        layout.addStretch(1)
