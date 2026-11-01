"""Centre view. Headless and offscreen stay on a label. PyVista loads on request."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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
        self._mesh: object | None = None
        self.clip_button = QPushButton(self.tr("Clip plane"))
        self.slice_button = QPushButton(self.tr("Slice plane"))
        self.reset_button = QPushButton(self.tr("Reset view"))
        tools = QHBoxLayout()
        for button in (self.clip_button, self.slice_button, self.reset_button):
            button.setEnabled(False)
            tools.addWidget(button)
        tools.addStretch(1)
        layout.addLayout(tools)
        self.clip_button.clicked.connect(lambda _checked=False: self.show_tool("clip"))
        self.slice_button.clicked.connect(lambda _checked=False: self.show_tool("slice"))
        self.reset_button.clicked.connect(lambda _checked=False: self.show_tool("plain"))

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
        if viewer_enabled():
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
            layout = self.layout()
            assert isinstance(layout, QVBoxLayout)
            layout.insertWidget(1, plot, 1)
            self._plot = plot
            self._mesh = mesh
            for button in (self.clip_button, self.slice_button, self.reset_button):
                button.setEnabled(True)
        except Exception as exc:
            return (
                f"PyVista could not build the view: {exc}\n\n"
                "Unset FOAMSTUDIO_VIEWER to keep the text summary, or run with a display."
            )
        return ""

    def show_tool(self, tool: str) -> None:
        """Interactive PyVista plane widgets: drag the plane to clip or slice the surface."""
        plot, mesh = self._plot, self._mesh
        if plot is None or mesh is None:
            return
        plot.clear_plane_widgets()  # type: ignore[attr-defined]
        plot.clear()  # type: ignore[attr-defined]
        if tool == "clip":
            plot.add_mesh_clip_plane(mesh)  # type: ignore[attr-defined]
        elif tool == "slice":
            plot.add_mesh(mesh, opacity=0.25)  # type: ignore[attr-defined]
            plot.add_mesh_slice(mesh, line_width=3)  # type: ignore[attr-defined]
        else:
            plot.add_mesh(mesh)  # type: ignore[attr-defined]
        plot.reset_camera()  # type: ignore[attr-defined]


def viewer_enabled() -> bool:
    """3D view on a real display by default; off when headless/offscreen or FOAMSTUDIO_VIEWER=0.

    FOAMSTUDIO_VIEWER=1 forces it on (tests that fake the plotter).
    """
    flag = os.environ.get("FOAMSTUDIO_VIEWER")
    if flag is not None:
        return flag == "1"
    if os.environ.get("FOAMSTUDIO_HEADLESS") == "1":
        return False
    return QGuiApplication.platformName() not in ("offscreen", "minimal")
