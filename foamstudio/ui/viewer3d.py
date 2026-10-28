"""Centre view. Headless and offscreen stay on a label. PyVista loads on request."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from foamstudio.core.geometry.model import Surface
from foamstudio.core.geometry.quality import colour_values


class Viewer3D(QWidget):
    patch_picked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("viewer3d")
        self.summary = QLabel(self.tr("No geometry loaded."))
        self.summary.setObjectName("viewerSummary")
        self.summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        self._plot: QWidget | None = None

    def set_surface(self, surface: Surface) -> str:
        count = len(surface.triangles)
        names = ", ".join(patch.name for patch in surface.patches)
        colours = colour_values([float(index) for index, _patch in enumerate(surface.patches)])
        self.summary.setText(
            self.tr("Loaded %1 triangles. Patches: %2. Colours: %3.")
            .replace("%1", str(count))
            .replace("%2", names or "(none)")
            .replace("%3", str(len(colours)))
        )
        if os.environ.get("FOAMSTUDIO_VIEWER") == "1":
            note = self._try_pyvista(surface)
            if note:
                self.summary.setText(self.summary.text() + "\n" + note)
        return self.summary.text()

    def _try_pyvista(self, surface: Surface) -> str:
        try:
            import pyvista as pv
            from pyvistaqt import QtInteractor
        except Exception as exc:
            return (
                f"PyVista did not import: {exc}\n\n"
                "Install pyvista and pyvistaqt. The patch list still works without them."
            )
        try:
            points: list[tuple[float, float, float]] = []
            faces: list[int] = []
            for triangle in surface.triangles:
                start = len(points)
                points.extend((triangle.a, triangle.b, triangle.c))
                faces.extend((3, start, start + 1, start + 2))
            if not faces:
                return "The surface has patches but no triangles to draw."
            mesh = pv.PolyData(points, faces)
            plot = QtInteractor(self)
            plot.add_mesh(mesh)
            self.layout().addWidget(plot)
            self._plot = plot
        except Exception as exc:
            return (
                f"PyVista could not build the view: {exc}\n\n"
                "Unset FOAMSTUDIO_VIEWER to keep the text summary, or run with a display."
            )
        return ""
