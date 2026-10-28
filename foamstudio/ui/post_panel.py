"""Results actions: write case.foam and a ParaView state. ParaView is not embedded."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class PostPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("postPanel")
        self.note = QLabel(
            self.tr(
                "Writes case.foam and a .pvsm state. ParaView opens as its own program. "
                "Slice, clip, iso-lines, and streamlines are computed without embedding ParaView."
            )
        )
        self.note.setWordWrap(True)
        self.export_button = QPushButton(self.tr("Write ParaView state"))
        self.export_button.setObjectName("writeParaViewState")
        layout = QVBoxLayout(self)
        layout.addWidget(self.note)
        layout.addWidget(self.export_button)
        layout.addStretch(1)
