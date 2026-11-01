"""blockMesh builder: kind, size, cells, and the patch roles sent to the generator."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

# Roles the generator's validateSpec accepts (SPEC_ROLES in openfoam_case_generator.html).
ROLES = ("inlet", "outlet", "wall", "freestream", "opening", "symmetry", "empty", "wedge", "cyclic")


def _length(value: float) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setDecimals(4)
    box.setRange(1e-4, 1e4)
    box.setSuffix(" m")
    box.setValue(value)
    return box


def _cells(value: int) -> QSpinBox:
    box = QSpinBox()
    box.setRange(1, 5000)
    box.setValue(value)
    return box


class MeshPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("meshPanel")
        self.kind = QComboBox()
        self.kind.setObjectName("meshKind")
        self.kind.addItems(["box", "channel", "wedge"])
        self.length = _length(1.0)
        self.height = _length(1.0)
        self.width = _length(0.1)
        self.nx = _cells(20)
        self.ny = _cells(20)
        self.nz = _cells(1)
        self.angle = QDoubleSpinBox()
        self.angle.setRange(0.5, 45.0)
        self.angle.setSuffix(" deg")
        self.angle.setValue(5.0)
        form = QFormLayout()
        form.addRow(self.tr("Kind"), self.kind)
        form.addRow(self.tr("Length (x)"), self.length)
        form.addRow(self.tr("Height (y) / radius"), self.height)
        form.addRow(self.tr("Width (z)"), self.width)
        form.addRow(self.tr("Cells x"), self.nx)
        form.addRow(self.tr("Cells y / radial"), self.ny)
        form.addRow(self.tr("Cells z (1 = 2D)"), self.nz)
        form.addRow(self.tr("Wedge angle"), self.angle)
        self.note = QLabel(
            self.tr("Writes system/blockMeshDict. Solver dictionaries stay in the generator.")
        )
        self.note.setWordWrap(True)
        self.write_button = QPushButton(self.tr("Write blockMeshDict"))
        self.write_button.setObjectName("writeBlockMesh")
        self.snappy_button = QPushButton(self.tr("Mesh around imported geometry (snappyHexMesh)"))
        self.snappy_button.setObjectName("writeSnappy")
        self.quality_button = QPushButton(self.tr("Show mesh quality (checkMesh sets)"))
        self.quality_button.setObjectName("showMeshQuality")
        self.patches = QTableWidget(0, 2)
        self.patches.setObjectName("patchRoles")
        self.patches.setHorizontalHeaderLabels([self.tr("Patch"), self.tr("Role")])
        self.patches.horizontalHeader().setStretchLastSection(True)
        self.patches.setMinimumHeight(160)
        self.send_button = QPushButton(self.tr("Send patch roles to Setup"))
        self.send_button.setObjectName("sendPatchRoles")
        self.send_button.setEnabled(False)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.note)
        layout.addWidget(self.write_button)
        layout.addWidget(self.snappy_button)
        layout.addWidget(self.quality_button)
        layout.addWidget(QLabel(self.tr("Patch roles (edit, then send to Setup)")))
        layout.addWidget(self.patches, 1)
        layout.addWidget(self.send_button)
        self.kind.currentTextChanged.connect(self._kind_changed)
        self._kind_changed(self.kind.currentText())

    def _kind_changed(self, kind: str) -> None:
        wedge = kind == "wedge"
        self.width.setEnabled(not wedge)
        self.nz.setEnabled(not wedge)
        self.angle.setEnabled(wedge)

    def params(self) -> dict[str, object]:
        """Keyword arguments for core.mesh.block_mesh_dict."""
        if self.kind.currentText() == "wedge":
            return {
                "length": self.length.value(),
                "radius": self.height.value(),
                "angle_deg": self.angle.value(),
                "cells": (self.nx.value(), self.ny.value(), 1),
            }
        return {
            "length": self.length.value(),
            "height": self.height.value(),
            "width": self.width.value(),
            "cells": (self.nx.value(), self.ny.value(), self.nz.value()),
        }

    def set_patches(self, rows: list[dict[str, str]]) -> None:
        self.patches.setRowCount(0)
        for row in rows:
            index = self.patches.rowCount()
            self.patches.insertRow(index)
            name = QLabel(row["name"])
            self.patches.setCellWidget(index, 0, name)
            role = QComboBox()
            role.addItems(ROLES)
            role.setCurrentText(row["role"])
            # Constraint types come from the mesh patch type; changing them here would
            # disagree with blockMeshDict, so they are shown but locked.
            role.setEnabled(row["role"] not in ("empty", "wedge", "symmetry", "cyclic"))
            self.patches.setCellWidget(index, 1, role)
        self.send_button.setEnabled(bool(rows))

    def patch_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for index in range(self.patches.rowCount()):
            name = self.patches.cellWidget(index, 0)
            role = self.patches.cellWidget(index, 1)
            if isinstance(name, QLabel) and isinstance(role, QComboBox):
                rows.append({"name": name.text(), "role": role.currentText()})
        return rows
