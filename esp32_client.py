from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket


class Esp32Client(QObject):
    """Reconnect automatically to an ESP32 Wi-Fi TCP endpoint."""

    status_changed = Signal(bool, str)
    message_received = Signal(str)

    def send_line(self, message: str) -> bool:
        if self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
            return False
        self.socket.write((message.rstrip("\r\n") + "\n").encode("utf-8"))
        self.socket.flush()
        return True

    def set_fence(self, latitude: float, longitude: float, radius: float, shape: str = "circle") -> bool:
        return self.send_line(f"SET_FENCE:{latitude:.8f},{longitude:.8f},{radius:.1f},{shape.lower()}")

    def set_demo_cow_position(self, latitude: float, longitude: float) -> bool:
        return self.send_line(f"DEMO_COW:{latitude:.8f},{longitude:.8f}")

    def clear_demo_cow_position(self) -> bool:
        return self.send_line("DEMO_COW:OFF")

    def __init__(self, host: str, port: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.host = host
        self.port = port
        self._online: bool | None = None
        self._buffer = ""
        self._last_message_at = 0.0
        self.socket = QTcpSocket(self)
        self.socket.connected.connect(self._connected)
        self.socket.disconnected.connect(lambda: self._set_status(False, "Connection lost"))
        self.socket.readyRead.connect(self._read)
        self.socket.errorOccurred.connect(self._error)
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setInterval(3000)
        self.reconnect_timer.timeout.connect(self.connect_to_device)
        self.health_timer = QTimer(self)
        self.health_timer.setInterval(1000)
        self.health_timer.timeout.connect(self._check_connection)

    def start(self) -> None:
        self.connect_to_device()
        self.reconnect_timer.start()
        self.health_timer.start()

    def stop(self) -> None:
        self.reconnect_timer.stop()
        self.health_timer.stop()
        self.socket.abort()

    def connect_to_device(self) -> None:
        if self.socket.state() in (
            QAbstractSocket.SocketState.ConnectedState,
            QAbstractSocket.SocketState.ConnectingState,
        ):
            return
        self.socket.abort()
        self.socket.connectToHost(self.host, self.port)

    def _connected(self) -> None:
        self._buffer = ""
        self._last_message_at = time.monotonic()
        self._set_status(True, f"{self.host}:{self.port}")
        self.socket.write(b"STATUS?\n")
        self.socket.flush()

    def _check_connection(self) -> None:
        if self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
            return
        elapsed = time.monotonic() - self._last_message_at
        if elapsed >= 7.0:
            self.socket.abort()
            self._buffer = ""
            self._set_status(False, "ESP32 heartbeat timed out")
        elif elapsed >= 3.0:
            self.send_line("PING")

    def _error(self, _error) -> None:
        self._set_status(False, self.socket.errorString())

    def _set_status(self, online: bool, detail: str) -> None:
        if online == self._online:
            return
        self._online = online
        self.status_changed.emit(online, detail)

    def _read(self) -> None:
        self._last_message_at = time.monotonic()
        self._buffer += bytes(self.socket.readAll()).decode("utf-8", errors="replace")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self.message_received.emit(line.strip())
