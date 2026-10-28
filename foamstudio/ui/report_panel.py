"""Report actions. HTML is built in core. PDF uses Qt's writer, not a new library."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class ReportPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("reportPanel")
        self.note = QLabel(self.tr("Writes an HTML report and, on request, a PDF of that HTML."))
        self.note.setWordWrap(True)
        self.html_button = QPushButton(self.tr("Write HTML report"))
        self.html_button.setObjectName("writeHtmlReport")
        self.pdf_button = QPushButton(self.tr("Write PDF report"))
        self.pdf_button.setObjectName("writePdfReport")
        layout = QVBoxLayout(self)
        layout.addWidget(self.note)
        layout.addWidget(self.html_button)
        layout.addWidget(self.pdf_button)
        layout.addStretch(1)


def write_pdf(html: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = QTextDocument()
    document.setHtml(html)
    writer = QPdfWriter(str(destination))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    document.print_(writer)
    if not destination.is_file() or destination.stat().st_size < 50:
        raise OSError(
            f"PDF writer did not produce {destination}.\n\n"
            "The HTML report is the source. Check that Qt can write PDF on this machine."
        )
    return destination
