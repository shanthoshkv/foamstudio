"""Dictionary editor: open/save case dictionaries, live checks, blockMeshDict preview signal."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def check_dictionary(text: str) -> list[str]:
    """Cheap OpenFOAM syntax checks: brace/paren balance and `key value` lines missing `;`."""
    problems: list[str] = []
    # line comments stripped per line: with re.S a `//.*` would eat the rest of the file
    body = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))
    for open_, close in ("{}", "()"):
        if body.count(open_) != body.count(close):
            problems.append(
                f"Unbalanced {open_}{close}: {body.count(open_)} vs {body.count(close)}"
            )
    depth = 0
    for number, line in enumerate(body.splitlines(), 1):
        stripped = line.strip()
        depth += stripped.count("(") - stripped.count(")")
        simple = re.fullmatch(r"[A-Za-z_][\w.:]*\s+[^{}()\s][^{}()]*", stripped)
        if depth == 0 and simple and not stripped.endswith(";") and not stripped.startswith("#"):
            problems.append(f"Line {number}: missing ';' after {stripped[:40]!r}")
    return problems


_KEYWORDS = re.compile(
    r"\b(FoamFile|dimensions|internalField|boundaryField|type|value|object|class)\b"
)


class _Highlighter(QSyntaxHighlighter):
    def __init__(self, parent: QWidget) -> None:
        document = parent.document() if isinstance(parent, QPlainTextEdit) else None
        super().__init__(document)
        self._format = QTextCharFormat()
        self._format.setForeground(QColor("#7fdbca"))

    def highlightBlock(self, text: str) -> None:
        for match in _KEYWORDS.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self._format)


class DictEditor(QWidget):
    preview = Signal(str)  # debounced text of a blockMeshDict being edited

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dictEditor")
        self._path: Path | None = None
        self.files = QComboBox()
        self.files.setObjectName("dictFiles")
        self.save_button = QPushButton(self.tr("Save"))
        self.save_button.setObjectName("dictSave")
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("dictText")
        self.editor.setPlaceholderText(
            self.tr(
                "Open a project, then pick a dictionary above. "
                "blockMeshDict previews in 3D as you type."
            )
        )
        self._highlighter = _Highlighter(self.editor)
        self.problems = QLabel("")
        self.problems.setObjectName("dictProblems")
        self.problems.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.files, 1)
        row.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.editor)
        layout.addWidget(self.problems)
        self._timer = QTimer(self, singleShot=True, interval=700)
        self._timer.timeout.connect(self._emit_preview)
        self.editor.textChanged.connect(self._changed)
        self.files.currentIndexChanged.connect(lambda _i: self.open_file(self.files.currentData()))
        self.save_button.clicked.connect(lambda _c=False: self.save())
        QShortcut(QKeySequence.StandardKey.Save, self, self.save)

    def load_case(self, case: Path) -> None:
        """List system/, constant/ and 0/ dictionaries; open blockMeshDict first when present."""
        self.files.blockSignals(True)
        self.files.clear()
        for folder in ("system", "constant", "0"):
            for path in sorted((case / folder).glob("*")) if (case / folder).is_dir() else []:
                if path.is_file():
                    self.files.addItem(f"{folder}/{path.name}", path)
        self.files.blockSignals(False)
        index = self.files.findText("system/blockMeshDict")
        self.files.setCurrentIndex(max(index, 0))
        self.open_file(self.files.currentData())

    def open_file(self, path: object) -> None:
        if not isinstance(path, Path):
            return
        self._path = path
        self.set_text(path.read_text(errors="replace"))

    def save(self) -> None:
        if self._path is None:
            return
        self._path.write_text(self.text(), newline="\n")
        self.problems.setText(self.tr("Saved %1").replace("%1", str(self._path)))

    def _changed(self) -> None:
        self.problems.setText("\n".join(check_dictionary(self.text())) or "OK")
        if self._path is not None and self._path.name == "blockMeshDict":
            self._timer.start()

    def _emit_preview(self) -> None:
        self.preview.emit(self.text())

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)

    def text(self) -> str:
        return self.editor.toPlainText()
