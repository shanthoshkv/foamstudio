"""Patch list. A click emits the patch name the generator should select."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from foamstudio.core.geometry.model import Surface


class PatchPanel(QWidget):
    patch_picked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("geometryPanel")
        self._surface: Surface | None = None
        self._note = QLabel(self.tr("No geometry loaded."))
        self._note.setWordWrap(True)
        self._list = QListWidget()
        self._list.setObjectName("patchList")
        self._list.itemClicked.connect(self._clicked)
        layout = QVBoxLayout(self)
        layout.addWidget(self._note)
        layout.addWidget(self._list)

    def set_surface(self, surface: Surface) -> None:
        self._surface = surface
        count = str(len(surface.patches))
        self._note.setText(
            self.tr("%1 patches from %2").replace("%1", count).replace("%2", surface.name)
        )
        self._list.clear()
        for patch in surface.patches:
            item = QListWidgetItem(f"{patch.name}  {patch.role}")
            item.setData(Qt.ItemDataRole.UserRole, patch.name)
            self._list.addItem(item)

    def _clicked(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(name, str):
            self.patch_picked.emit(name)
