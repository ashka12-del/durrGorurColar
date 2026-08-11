from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from styles.theme import ACCENT, DANGER, INFO, MUTED, WARNING
from widgets.common import PageHeader, StatCard


class DashboardPage(QWidget):
    fence_submitted = Signal(float, float, float)
    fence_previewed = Signal(float, float, float)

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)
        root.addWidget(PageHeader("Dashboard", "Live ESP32 sensor, GPS, and virtual-fence telemetry."))
        columns = QHBoxLayout()
        columns.setSpacing(10)

        telemetry = QFrame(objectName="card")
        telemetry_layout = QVBoxLayout(telemetry)
        telemetry_layout.setContentsMargins(10, 8, 10, 8)
        telemetry_layout.setSpacing(4)
        title = QLabel("LIVE TELEMETRY")
        title.setStyleSheet("font-size:16px;font-weight:800")
        self.updated_label = QLabel("Waiting for ESP32 telemetry…")
        self.updated_label.setObjectName("muted")
        telemetry_layout.addWidget(title)
        telemetry_layout.addWidget(self.updated_label)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.status_labels = {}
        for device, title in (
            ("esp32", "ESP32"),
            ("mpu6050", "MPU6050"),
            ("ds18b20", "DS18B20"),
            ("gps", "GPS"),
        ):
            label = QLabel(f"{title} WAITING")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(self._status_style(None))
            status_row.addWidget(label, 1)
            self.status_labels[device] = label
        telemetry_layout.addLayout(status_row)
        self._esp_online = False
        self._mpu_online = False
        self._temperature_online = False
        self._gps_online = False
        self._current_latitude: float | None = None
        self._current_longitude: float | None = None
        grid = QGridLayout()
        grid.setSpacing(6)
        self.cards = {
            "latitude": StatCard("Latitude", "—", "LAT", INFO, "Decimal degrees"),
            "longitude": StatCard("Longitude", "—", "LON", INFO, "Decimal degrees"),
            "altitude": StatCard("Altitude", "—", "ALT", ACCENT, "Meters above sea level"),
            "temperature": StatCard("Temperature", "—", "°C", WARNING, "ESP32 sensor"),
            "distance": StatCard("Fence boundary distance", "—", "m", ACCENT, "Positive inside • negative outside"),
            "fence": StatCard("Fence status", "Waiting", "●", ACCENT, "Virtual fence"),
            "acceleration_x": StatCard("Acceleration X", "—", "X", INFO, "MPU6050 • g"),
            "acceleration_y": StatCard("Acceleration Y", "—", "Y", INFO, "MPU6050 • g"),
            "acceleration_z": StatCard("Acceleration Z", "—", "Z", INFO, "MPU6050 • g"),
        }
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 3, index % 3)
        telemetry_layout.addLayout(grid)
        columns.addWidget(telemetry, 2)

        fence = QFrame(objectName="card")
        fence_layout = QVBoxLayout(fence)
        fence_layout.setContentsMargins(12, 10, 12, 10)
        fence_layout.setSpacing(6)
        fence_title = QLabel("VIRTUAL FENCE INPUT")
        fence_title.setStyleSheet("font-size:16px;font-weight:800")
        fence_layout.addWidget(fence_title)
        note = QLabel("Set the circular virtual-fence radius in meters.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{MUTED}")
        fence_layout.addWidget(note)
        form = QFormLayout()
        self.radius = self._coordinate_input(1, 100000, 250, 1)
        self.radius.setSuffix(" m")
        self.radius.valueChanged.connect(self._preview_fence)
        form.addRow("Radius", self.radius)
        fence_layout.addLayout(form)
        self.apply_button = QPushButton("Apply / Update Fence")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self._submit_fence)
        fence_layout.addWidget(self.apply_button)
        self.fence_feedback = QLabel("No fence update sent in this session.")
        self.fence_feedback.setWordWrap(True)
        self.fence_feedback.setObjectName("muted")
        fence_layout.addWidget(self.fence_feedback)
        fence_layout.addStretch()
        columns.addWidget(fence, 1)
        root.addLayout(columns)

    @staticmethod
    def _coordinate_input(minimum: float, maximum: float, value: float, decimals: int = 6) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(minimum, maximum)
        field.setDecimals(decimals)
        field.setValue(value)
        field.setSingleStep(0.0001 if decimals > 1 else 1)
        field.setAccelerated(True)
        field.setKeyboardTracking(True)
        return field

    def _submit_fence(self) -> None:
        if self._current_latitude is None or self._current_longitude is None:
            self.set_fence_feedback("Cannot create fence: waiting for a valid GPS fix.", False)
            return
        self.fence_submitted.emit(self._current_latitude, self._current_longitude, self.radius.value())

    def _preview_fence(self, _value: float) -> None:
        if self._current_latitude is not None and self._current_longitude is not None:
            self.fence_previewed.emit(self._current_latitude, self._current_longitude, self.radius.value())

    def set_fence_inputs(self, latitude: float, longitude: float, radius: float) -> None:
        self.radius.blockSignals(True)
        self.radius.setValue(radius)
        self.radius.blockSignals(False)

    def set_fence_feedback(self, message: str, success: bool = True) -> None:
        self.fence_feedback.setText(message)
        self.fence_feedback.setStyleSheet(f"color:{ACCENT if success else WARNING}")

    def set_device_status(self, device: str, online: bool) -> None:
        if device == "esp32":
            self._esp_online = online
            if not online:
                self._mpu_online = False
                self._temperature_online = False
                self._gps_online = False
                self.updated_label.setText("ESP32 offline - showing last received values")
        elif device == "mpu6050":
            self._mpu_online = online
        elif device == "ds18b20":
            self._temperature_online = online
        elif device == "gps":
            self._gps_online = online

        states = {
            "esp32": self._esp_online,
            "mpu6050": self._mpu_online,
            "ds18b20": self._temperature_online,
            "gps": self._gps_online,
        }
        titles = {"esp32": "ESP32", "mpu6050": "MPU6050", "ds18b20": "DS18B20", "gps": "GPS"}
        for name, state in states.items():
            self.status_labels[name].setText(f"{titles[name]} {'ONLINE' if state else 'OFFLINE'}")
            self.status_labels[name].setStyleSheet(self._status_style(state))

    @staticmethod
    def _status_style(online: bool | None) -> str:
        if online is None:
            color, background = WARNING, "#2a2613"
        elif online:
            color, background = ACCENT, "#102d26"
        else:
            color, background = DANGER, "#35171c"
        return (
            f"color:{color};background:{background};border:1px solid {color};"
            "border-radius:9px;padding:7px 8px;font-weight:800"
        )

    def update_telemetry(self, data: dict) -> None:
        def number(key: str, suffix: str, precision: int) -> str:
            value = data.get(key)
            return "—" if value is None else f"{float(value):.{precision}f}{suffix}"
        self.cards["latitude"].set_value(number("latitude", "", 6))
        self.cards["longitude"].set_value(number("longitude", "", 6))
        self.cards["altitude"].set_value(number("altitude", " m", 1))
        self.cards["temperature"].set_value(number("temperature", "°C", 1))
        self.cards["distance"].set_value(number("fence_distance", " m", 1))
        self.cards["acceleration_x"].set_value(number("acceleration_x", " g", 3))
        self.cards["acceleration_y"].set_value(number("acceleration_y", " g", 3))
        self.cards["acceleration_z"].set_value(number("acceleration_z", " g", 3))
        status = str(data.get("fence_status", "Unknown")).title()
        self.cards["fence"].set_value(status)
        self.updated_label.setText(f"Last packet: {data.get('received_at', 'just now')}")
        if data.get("gps_valid", False):
            try:
                self._current_latitude = float(data["latitude"])
                self._current_longitude = float(data["longitude"])
            except (KeyError, TypeError, ValueError):
                pass
