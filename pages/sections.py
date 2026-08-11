from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from styles.theme import ACCENT, DANGER, INFO, MUTED, WARNING
from widgets.common import PageHeader
from widgets.map_widget import TelemetryMap


class MapPage(QWidget):
    fence_submitted = Signal(float, float, float)
    fence_previewed = Signal(float, float, float)

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("GPS Map", "Live cattle position and interactive virtual-fence control."))
        frame = QFrame(objectName="card")
        layout = QVBoxLayout(frame)
        self.summary = QLabel("Waiting for GPS telemetry…")
        self.summary.setObjectName("muted")
        self.map = TelemetryMap()
        self.map.fence_previewed.connect(self.fence_previewed.emit)
        self.map.fence_dropped.connect(self._fence_moved)
        self.hint = QLabel("Hover red dot for GPS coordinates  •  Hover fence edge for radius and distance")
        self.hint.setStyleSheet(f"color:{MUTED};font-weight:700")
        controls = QHBoxLayout()
        controls.addStretch()
        self.edit_button = QPushButton("Edit Fence")
        self.edit_button.clicked.connect(self._begin_edit)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel_edit)
        self.cancel_button.setVisible(False)
        self.update_button = QPushButton("Update Fence")
        self.update_button.setObjectName("primary")
        self.update_button.clicked.connect(self._apply_edit)
        self.update_button.setVisible(False)
        controls.addWidget(self.edit_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.update_button)
        self._original_fence: tuple[float, float, float] | None = None
        layout.addWidget(self.summary)
        layout.addWidget(self.hint)
        layout.addLayout(controls)
        layout.addWidget(self.map)
        root.addWidget(frame)

    def update_telemetry(self, data: dict) -> None:
        self.map.set_telemetry(data)
        if data.get("latitude") is not None and data.get("longitude") is not None:
            self.summary.setText(f"{float(data['latitude']):.6f}, {float(data['longitude']):.6f}  •  {data.get('fence_status', 'Unknown')}")

    def set_fence(self, latitude: float, longitude: float, radius: float) -> None:
        self.map.set_fence(latitude, longitude, radius)

    def _begin_edit(self) -> None:
        self._original_fence = self.map.fence
        self.map.set_editable(True)
        self.edit_button.setVisible(False)
        self.cancel_button.setVisible(True)
        self.update_button.setVisible(True)
        self.update_button.setEnabled(False)
        self.hint.setText("EDIT MODE  •  Drag the green fence, then select Update Fence  •  Hover markers for details")

    def _fence_moved(self, _latitude: float, _longitude: float, _radius: float) -> None:
        self.update_button.setEnabled(True)

    def _apply_edit(self) -> None:
        if self.map.fence:
            self.fence_submitted.emit(*self.map.fence)
        self._finish_edit()

    def _cancel_edit(self) -> None:
        if self._original_fence:
            self.map.set_fence(*self._original_fence)
            self.fence_previewed.emit(*self._original_fence)
        self._finish_edit()

    def _finish_edit(self) -> None:
        self.map.set_editable(False)
        self.edit_button.setVisible(True)
        self.cancel_button.setVisible(False)
        self.update_button.setVisible(False)
        self.hint.setText("Hover red dot for GPS coordinates  •  Hover fence edge for radius and distance")
        self._original_fence = None


class AlertsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("Alerts", "Fence breaches, abnormal temperature, and ESP32 system notifications."))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Time", "Type", "Message", "Severity"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table)

    def add_alert(self, alert: dict) -> None:
        self.table.insertRow(0)
        values = [alert.get("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")), alert.get("type", "System"), alert.get("message", "Notification"), alert.get("severity", "Info")]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column == 3: item.setForeground(QColor({"Critical": DANGER, "Warning": WARNING}.get(str(value), INFO)))
            self.table.setItem(0, column, item)


class HistoryPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("History", "Telemetry and alert records received during this session."))
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Time", "Record", "Latitude", "Longitude", "Altitude", "Temperature", "Details"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table)

    def add_telemetry(self, data: dict) -> None:
        motion = f"Accel X/Y/Z: {data.get('acceleration_x', '—')}, {data.get('acceleration_y', '—')}, {data.get('acceleration_z', '—')} g"
        self._add([data.get("received_at", ""), "Telemetry", data.get("latitude", "—"), data.get("longitude", "—"), data.get("altitude", "—"), data.get("temperature", "—"), f"Fence: {data.get('fence_status', 'Unknown')} • {motion}"])

    def add_alert(self, alert: dict) -> None:
        self._add([alert.get("time", ""), "Alert", "—", "—", "—", "—", alert.get("message", "")])

    def _add(self, values: list) -> None:
        self.table.insertRow(0)
        for column, value in enumerate(values): self.table.setItem(0, column, QTableWidgetItem(str(value)))
        if self.table.rowCount() > 1000: self.table.removeRow(self.table.rowCount() - 1)


class AboutPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("About", "NeuroGoru smart livestock safety and monitoring system."))
        card = QFrame(objectName="card")
        layout = QVBoxLayout(card)
        title = QLabel("NeuroGoru")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size:34px;font-weight:900;color:{ACCENT}")
        description = QLabel("Smart Virtual Fence & Livestock Monitoring System\n\nNeuroGoru combines an ESP32, GPS receiver, temperature sensor, local Wi-Fi communication, and a desktop dashboard to monitor cattle location and wellbeing. The circular virtual fence provides immediate breach awareness without requiring internet access.\n\nSystem components\n• ESP32 controller and local Wi-Fi TCP server\n• GPS location and altitude telemetry\n• Temperature sensing\n• Configurable circular virtual fence\n• Live alerts and telemetry history\n\nVersion 1.0 • Academic prototype")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        description.setStyleSheet(f"color:{MUTED};font-size:14px")
        layout.addWidget(title); layout.addWidget(description)
        root.addWidget(card); root.addStretch()
