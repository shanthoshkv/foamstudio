"""Plain dictionary editor with keyword highlighting. No QScintilla."""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


def check_dictionary(text: str) -> list[str]:
    """Cheap OpenFOAM syntax checks: brace/paren balance and `key value` lines missing `;`."""
    problems: list[str] = []
    body = re.sub(r"//.*|/\*.*?\*/", "", text, flags=re.S)
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
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dictEditor")
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("dictText")
        self.editor.setPlaceholderText(
            self.tr("Dictionary text. Manual edits are kept in the project.")
        )
        self._highlighter = _Highlighter(self.editor)
        self.problems = QLabel("")
        self.problems.setObjectName("dictProblems")
        self.problems.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addWidget(self.problems)
        self.editor.textChanged.connect(
            lambda: self.problems.setText("\n".join(check_dictionary(self.text())) or "OK")
        )

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)

    def text(self) -> str:
        return self.editor.toPlainText()
