"""Plain dictionary editor with keyword highlighting. No QScintilla."""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

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
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dictEditor")
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("dictText")
        self.editor.setPlaceholderText(
            self.tr("Dictionary text. Manual edits are kept in the project.")
        )
        self._highlighter = _Highlighter(self.editor)
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)

    def text(self) -> str:
        return self.editor.toPlainText()
