"""One FoamStudio process per instance key."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, key: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._server: QLocalServer | None = None
        self.already_running = False
        if self._claim_as_client(key):
            self.already_running = True
            return
        QLocalServer.removeServer(key)
        server = QLocalServer(self)
        if server.listen(key):
            server.newConnection.connect(self._on_connection)
            self._server = server
            return
        if self._claim_as_client(key):
            self.already_running = True
            return
        raise RuntimeError(
            f"Single-instance setup failed for {key!r}: {server.errorString()}. "
            "Close the other FoamStudio process or set FOAMSTUDIO_INSTANCE_KEY."
        )

    def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        QLocalServer.removeServer(self._key)
        self._server = None

    def _claim_as_client(self, key: str) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(key)
        if not socket.waitForConnected(500):
            socket.abort()
            return False
        socket.write(b"raise")
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return True

    def _on_connection(self) -> None:
        if self._server is None:
            return
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        socket.waitForReadyRead(200)
        socket.disconnectFromServer()
        self.activated.emit()
