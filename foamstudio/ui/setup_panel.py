"""Hosts the case generator. The WebEngine view is created only when the panel is opened."""

from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from foamstudio.generator.headless import GeneratorFailure


class SetupPanel(QWidget):
    write_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("setupPanel")
        self.session: object | None = None
        self.spec_text: str | None = None
        layout = QVBoxLayout(self)
        self.status = QLabel(self.tr("The case generator opens in this panel."))
        self.status.setObjectName("setupStatus")
        self.status.setWordWrap(True)
        self.write_button = QPushButton(self.tr("Write case"))
        self.write_button.setObjectName("writeCaseButton")
        self.write_button.clicked.connect(lambda _checked=False: self.write_requested.emit())
        layout.addWidget(self.status, 1)
        layout.addWidget(self.write_button)
        self._layout = layout

    def load_generator(self) -> None:
        if os.environ.get("FOAMSTUDIO_HEADLESS") == "1":
            raise GeneratorFailure(
                command="QWebEngineView openfoam_case_generator.html",
                returncode=1,
                log_tail="FOAMSTUDIO_HEADLESS=1",
                suggestion=(
                    "Unset FOAMSTUDIO_HEADLESS to open the case generator, or write the case with "
                    "foamstudio --write-case case.json --project <folder>."
                ),
            )
        if self.session is None:
            from foamstudio.generator.bridge import GeneratorSession

            session = GeneratorSession(self)
            session.bridge.spec_changed.connect(self._store_spec)
            # The web form takes the space; the status label shrinks to one line.
            self._layout.insertWidget(0, session.view, 1)
            self._layout.setStretchFactor(self.status, 0)
            self.status.setText(self.tr("Loading the case generator..."))
            session.load()
            self.session = session
        self.status.setText(self.tr("Case generator ready."))

    def _store_spec(self, payload: str) -> None:
        self.spec_text = payload
