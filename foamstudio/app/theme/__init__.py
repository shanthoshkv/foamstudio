"""Dark and light stylesheets. Colours follow the case generator."""

from __future__ import annotations

from importlib.resources import files

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

THEMES = ("dark", "light")


def load_qss(theme: str) -> str:
    if theme not in THEMES:
        raise ValueError(f"Unknown theme {theme!r}. Expected one of {THEMES}.")
    resource = files("foamstudio.app.theme").joinpath(f"{theme}.qss")
    if not resource.is_file():
        raise FileNotFoundError(f"Theme stylesheet is missing: {theme}.qss")
    return resource.read_text(encoding="utf-8")


def load_icon() -> QIcon:
    resource = files("foamstudio.app.theme").joinpath("foam.svg")
    if not resource.is_file():
        raise FileNotFoundError("Application icon is missing: foam.svg")
    renderer = QSvgRenderer(QByteArray(resource.read_bytes()))
    if not renderer.isValid():
        raise RuntimeError("Application icon foam.svg is not valid SVG.")
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    icon = QIcon(QPixmap.fromImage(image))
    if icon.isNull():
        raise RuntimeError("Qt could not build an icon from foam.svg.")
    return icon


def mono_font(point_size: int) -> QFont:
    font = QFont()
    font.setFamilies(
        [
            "Cascadia Mono",
            "JetBrains Mono",
            "Consolas",
            "Menlo",
            "DejaVu Sans Mono",
            "monospace",
        ]
    )
    font.setPointSize(point_size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font
