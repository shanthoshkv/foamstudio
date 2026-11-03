"""Command palette (Ctrl+K), shortcut sheet (F1), Python console."""

from __future__ import annotations

import code
import contextlib
import io

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


def menu_actions(window: QMainWindow) -> list[tuple[str, QAction]]:
    found: list[tuple[str, QAction]] = []

    def walk(path: str, actions: list[QAction]) -> None:
        for action in actions:
            menu = action.menu()
            text = action.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
            if menu is not None:
                walk(f"{path}{text} > ", menu.actions())  # type: ignore[attr-defined]
            elif text and not action.isSeparator():
                found.append((path + text, action))

    walk("", window.menuBar().actions())
    return found


class CommandPalette(QDialog):
    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.setObjectName("commandPalette")
        self.setWindowTitle(self.tr("Command palette"))
        self.resize(520, 380)
        self.query = QLineEdit(placeholderText=self.tr("Type a command..."))
        self.list = QListWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.query)
        layout.addWidget(self.list)
        self._actions = menu_actions(window)
        self.query.textChanged.connect(self._filter)
        self.query.returnPressed.connect(self._go)
        self.list.itemActivated.connect(lambda _i: self._go())
        self._filter("")

    def _filter(self, text: str) -> None:
        self.list.clear()
        words = text.lower().split()
        for label, action in self._actions:
            if all(w in label.lower() for w in words):
                shortcut = action.shortcut().toString()
                item = QListWidgetItem(f"{label}    {shortcut}".rstrip())
                item.setData(Qt.ItemDataRole.UserRole, action)
                item.setFlags(item.flags() if action.isEnabled() else Qt.ItemFlag.NoItemFlags)
                self.list.addItem(item)
        self.list.setCurrentRow(0)

    def _go(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        action = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if isinstance(action, QAction):
            action.trigger()


def shortcut_sheet(window: QMainWindow) -> QDialog:
    dialog = QDialog(window)
    dialog.setWindowTitle(dialog.tr("Keyboard shortcuts"))
    dialog.resize(520, 480)
    view = QPlainTextEdit(readOnly=True)
    rows = [("Ctrl+K", "Command palette"), ("F1", "This sheet")]
    rows += [
        (a.shortcut().toString(), label)
        for label, a in menu_actions(window)
        if not a.shortcut().isEmpty()
    ]
    view.setPlainText("\n".join(f"{k:16} {v}" for k, v in rows))
    QVBoxLayout(dialog).addWidget(view)
    return dialog


class PythonConsole(QWidget):
    """`window`, `project`, `case` preloaded. Runs on the GUI thread: keep it short."""

    def __init__(self, namespace: dict[str, object], parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(self.tr("Python console"))
        self.resize(760, 480)
        self.out = QPlainTextEdit(readOnly=True)
        self.out.setObjectName("consoleOutput")
        self.line = QLineEdit(placeholderText=">>> ")
        self.line.setObjectName("consoleInput")
        layout = QVBoxLayout(self)
        layout.addWidget(self.out)
        layout.addWidget(self.line)
        self._console = code.InteractiveConsole(namespace)
        self.line.returnPressed.connect(self._run)
        self.out.appendPlainText("Names: " + ", ".join(namespace))

    def _run(self) -> None:
        source = self.line.text()
        self.line.clear()
        self.out.appendPlainText(">>> " + source)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            self._console.push(source)
        if buffer.getvalue():
            self.out.appendPlainText(buffer.getvalue().rstrip())
