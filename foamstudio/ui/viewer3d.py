"""Centre view. Headless and offscreen stay on a label. PyVista loads on request."""

from __future__ import annotations

import os
from typing import Any

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
        self.pick_button = QPushButton(self.tr("Pick faces"))
        self.pick_button.setToolTip(
            self.tr("Drag a box over boundary faces (press r in the view) to name them")
        )
        self.on_pick = None  # callable(lo, hi) set by the host
        tools = QHBoxLayout()
        for button in (self.clip_button, self.slice_button, self.reset_button, self.pick_button):
            button.setEnabled(False)
            tools.addWidget(button)
        tools.addStretch(1)
        layout.addLayout(tools)
        self.clip_button.clicked.connect(lambda _checked=False: self.show_tool("clip"))
        self.slice_button.clicked.connect(lambda _checked=False: self.show_tool("slice"))
        self.reset_button.clicked.connect(lambda _checked=False: self.show_tool("plain"))
        self.pick_button.clicked.connect(lambda _checked=False: self.start_pick())

    def start_pick(self) -> None:
        """Rubber-band pick of visible cells/faces; reports their bounding box to on_pick."""
        plot: Any = self._plot
        if plot is None:
            return

        def picked(sel: object) -> None:
            b = getattr(sel, "bounds", None)
            if b is None or getattr(sel, "n_cells", 0) == 0:
                return
            lo, hi = (b[0], b[2], b[4]), (b[1], b[3], b[5])
            self.summary.setText(f"Picked {sel.n_cells} faces in box {lo} - {hi}")  # type: ignore[attr-defined]
            if self.on_pick:
                self.on_pick(lo, hi)

        plot.enable_cell_picking(
            callback=picked, through=False, show_message="Press r, then drag a box over faces"
        )

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

    def show_cells(self, case: object, sets: dict[str, list[int]], text: str) -> None:
        """Faint mesh with the flagged cells in red. The text summary works without PyVista."""
        self.summary.setText(text)
        if not sets or not viewer_enabled():
            return
        try:
            from pathlib import Path

            import pyvista as pv
            from pyvistaqt import QtInteractor

            marker = Path(str(case)) / "case.foam"
            marker.touch()
            reader = pv.OpenFOAMReader(str(marker))
            reader.decompose_polyhedra = False  # keep OpenFOAM cell numbering
            mesh = reader.read()["internalMesh"]
            ids = sorted({i for cells in sets.values() for i in cells if i < mesh.n_cells})
            if self._plot is None:
                plot = QtInteractor(self)
                layout = self.layout()
                assert isinstance(layout, QVBoxLayout)
                layout.insertWidget(1, plot, 1)
                self._plot = plot
            plot = self._plot
            plot.clear()  # type: ignore[attr-defined]
            plot.add_mesh(mesh, style="wireframe", opacity=0.08)  # type: ignore[attr-defined]
            plot.add_mesh(mesh.extract_cells(ids), color="red")  # type: ignore[attr-defined]
            plot.reset_camera()  # type: ignore[attr-defined]
            self._mesh = mesh
        except Exception as exc:
            self.summary.setText(f"{text}\n\nThe 3D view could not load the mesh: {exc}")

    def _plotter(self) -> object:
        from pyvistaqt import QtInteractor

        if self._plot is None:
            plot = QtInteractor(self)
            layout = self.layout()
            assert isinstance(layout, QVBoxLayout)
            layout.insertWidget(1, plot, 1)
            self._plot = plot
            for button in (self.clip_button, self.slice_button, self.reset_button):
                button.setEnabled(True)
        return self._plot

    def show_blocks(
        self, points: list[tuple[float, float, float]], hexes: list[tuple[int, ...]]
    ) -> str:
        """blockMesh blocks as an outline, straight from the dictionary text (no OpenFOAM run)."""
        text = f"Preview: {len(hexes)} blocks, {len(points)} vertices (unsaved edits)"
        self.summary.setText(text)
        if not viewer_enabled():
            return text
        try:
            import numpy as np
            import pyvista as pv

            cells = np.hstack([[8, *h] for h in hexes])
            grid = pv.UnstructuredGrid(cells, np.full(len(hexes), 12, np.uint8), np.array(points))
            plot = self._plotter()
            plot.clear()  # type: ignore[attr-defined]
            plot.add_mesh(grid, opacity=0.25, color="#5fb3d4")  # type: ignore[attr-defined]
            plot.add_mesh(grid.extract_all_edges(), color="white")  # type: ignore[attr-defined]
            plot.add_point_labels(
                np.array(points), [str(i) for i in range(len(points))], point_size=6, font_size=10
            )  # type: ignore[attr-defined]
            plot.reset_camera()  # type: ignore[attr-defined]
            b = grid.bounds
            if b[5] - b[4] < 0.05 * max(b[1] - b[0], b[3] - b[2]):  # 2D case: look straight down
                plot.view_xy()  # type: ignore[attr-defined]
        except Exception as exc:
            text = f"{text}\n\nPreview failed: {exc}"
            self.summary.setText(text)
        return text

    def show_case(self, case: object, field: str | None) -> str:
        """polyMesh with patches (field None) or the latest-time field on the internal mesh."""
        from pathlib import Path

        root = Path(str(case))
        if not (root / "constant" / "polyMesh" / "faces").is_file():
            text = self.tr("No polyMesh yet: run blockMesh (Mesh tab > Re-mesh) first.")
            self.summary.setText(text)
            return text
        text = (
            self.tr("Mesh: %1").replace("%1", str(root))
            if field is None
            else f"{field} at the latest time"
        )
        self.summary.setText(text)
        if not viewer_enabled():
            return text
        try:
            import pyvista as pv

            marker = root / "case.foam"
            marker.touch()
            reader = pv.OpenFOAMReader(str(marker))
            if field is not None and reader.time_values:
                reader.set_active_time_value(reader.time_values[-1])
            data = reader.read()
            plot = self._plotter()
            plot.clear()  # type: ignore[attr-defined]
            if field is None:
                patches = data["boundary"]
                for index, name in enumerate(patches.keys()):
                    plot.add_mesh(
                        patches[name], color=pv.Color(f"C{index % 10}"), show_edges=True, label=name
                    )  # type: ignore[attr-defined]
                plot.add_legend()  # type: ignore[attr-defined]
                self._mesh = data["internalMesh"]
            else:
                mesh = data["internalMesh"]
                if field not in mesh.array_names:
                    raise ValueError(
                        f"{field} is not in the latest time ({', '.join(mesh.array_names)})"
                    )
                plot.add_mesh(mesh, scalars=field, show_scalar_bar=True)  # type: ignore[attr-defined]
                self._mesh = mesh
            plot.reset_camera()  # type: ignore[attr-defined]
            b = self._mesh.bounds
            if b[5] - b[4] < 0.05 * max(b[1] - b[0], b[3] - b[2]):  # one-cell-thick 2D case
                plot.view_xy()  # type: ignore[attr-defined]
        except Exception as exc:
            text = f"{text}\n\nThe 3D view could not load the case: {exc}"
            self.summary.setText(text)
        return text

    def _reader(self, case: object) -> object:
        from pathlib import Path

        import pyvista as pv

        marker = Path(str(case)) / "case.foam"
        marker.touch()
        return pv.OpenFOAMReader(str(marker))

    def streamlines(self, case: object, seeds: int = 200) -> str:
        """Streamlines of U at the latest time, seeded from random internal points."""
        if not viewer_enabled():
            return "Streamlines need the 3D view."
        try:
            reader = self._reader(case)
            reader.set_active_time_value(reader.time_values[-1])  # type: ignore[attr-defined]
            mesh = reader.read()["internalMesh"].cell_data_to_point_data()  # type: ignore[attr-defined]
            lines = mesh.streamlines(vectors="U", n_points=seeds, source_radius=mesh.length / 4)
            plot = self._plotter()
            plot.clear()  # type: ignore[attr-defined]
            plot.add_mesh(mesh.outline(), color="grey")  # type: ignore[attr-defined]
            plot.add_mesh(lines.tube(radius=mesh.length / 800), scalars="U")  # type: ignore[attr-defined]
            plot.reset_camera()  # type: ignore[attr-defined]
            text = f"{lines.n_lines} streamlines of U"
        except Exception as exc:
            text = f"Streamlines failed: {exc}"
        self.summary.setText(text)
        return text

    def line_values(
        self, case: object, field: str, a: tuple[float, ...], b: tuple[float, ...], n: int = 200
    ) -> tuple[list[float], list[float]]:
        """Probe: field (or its magnitude) along the segment a-b at the latest time."""
        import numpy as np

        reader = self._reader(case)
        reader.set_active_time_value(reader.time_values[-1])  # type: ignore[attr-defined]
        mesh = reader.read()["internalMesh"]  # type: ignore[attr-defined]
        line = mesh.sample_over_line(a, b, resolution=n - 1)
        values = np.asarray(line[field])
        if values.ndim > 1:
            values = np.linalg.norm(values, axis=1)
        distance = np.linspace(0.0, float(np.linalg.norm(np.subtract(b, a))), len(values))
        return distance.tolist(), values.tolist()

    def animate(self, case: object, field: str, interval_ms: int = 400) -> str:
        """Step the field through every written time on a QTimer."""
        from PySide6.QtCore import QTimer

        if not viewer_enabled():
            return "Animation needs the 3D view."
        try:
            reader = self._reader(case)
            times = list(reader.time_values)  # type: ignore[attr-defined]
        except Exception as exc:
            return f"Animation failed: {exc}"
        if not times:
            return "No time directories to animate."
        frames = iter(times)
        timer = QTimer(self)

        def step() -> None:
            try:
                t = next(frames)
            except StopIteration:
                timer.stop()
                return
            reader.set_active_time_value(t)  # type: ignore[attr-defined]
            mesh = reader.read()["internalMesh"]  # type: ignore[attr-defined]
            plot = self._plotter()
            plot.clear()  # type: ignore[attr-defined]
            if field in mesh.array_names:
                plot.add_mesh(mesh, scalars=field)  # type: ignore[attr-defined]
            self.summary.setText(f"{field} at t = {t:g}")

        timer.timeout.connect(step)
        timer.start(interval_ms)
        self._animation = timer
        return f"Animating {field} over {len(times)} times"

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
