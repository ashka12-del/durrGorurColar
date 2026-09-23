from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from esp32_client import Esp32Client
from pages.dashboard import DashboardPage
from pages.sections import AboutPage, AlertsPage, HistoryPage, MapPage
from styles.theme import ACCENT, stylesheet


class BackgroundWidget(QWidget):
    def __init__(self, image_path: Path) -> None:
        super().__init__(objectName="root"); self._background = QPixmap(str(image_path))
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if not self._background.isNull():
            scaled = self._background.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(0, 0, scaled, (scaled.width()-self.width())//2, (scaled.height()-self.height())//2, self.width(), self.height())
        else: painter.fillRect(self.rect(), QColor("#08111f"))
        painter.fillRect(self.rect(), QColor(3, 10, 20, 150)); super().paintEvent(event)


class StatusLog(QFrame):
    COLORS = {"Info": "#36bffa", "Success": "#32d583", "Warning": "#fdb022", "Critical": "#f04438"}

    def __init__(self) -> None:
        super().__init__(objectName="statusLog")
        self.setFixedHeight(132)
        root = QVBoxLayout(self); root.setContentsMargins(18, 10, 18, 12); root.setSpacing(7)
        header = QHBoxLayout()
        header.addWidget(QLabel("SYSTEM STATUS LOG", objectName="logTitle"))
        header.addWidget(QLabel("● LIVE", objectName="liveBadge")); header.addStretch()
        clear = QPushButton("Clear", objectName="logClear"); clear.clicked.connect(self.clear); header.addWidget(clear)
        root.addLayout(header)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget(); self.rows = QVBoxLayout(self.container)
        self.rows.setContentsMargins(0, 0, 0, 0); self.rows.setSpacing(4); self.rows.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.container); root.addWidget(scroll)

    def add(self, message: str, level: str = "Info", source: str = "System") -> None:
        color = self.COLORS.get(level, self.COLORS["Info"])
        row = QFrame(objectName="logRow"); row.setStyleSheet(f"QFrame#logRow{{border-left:3px solid {color};}}")
        layout = QHBoxLayout(row); layout.setContentsMargins(10, 4, 10, 4); layout.setSpacing(12)
        time = QLabel(datetime.now().strftime("%H:%M:%S"), objectName="logTime"); time.setFixedWidth(64)
        badge = QLabel(level.upper()); badge.setFixedWidth(72); badge.setStyleSheet(f"color:{color};font-weight:900;font-size:10px")
        source_label = QLabel(source.upper(), objectName="logSource"); source_label.setFixedWidth(100)
        text = QLabel(message); text.setWordWrap(True)
        layout.addWidget(time); layout.addWidget(badge); layout.addWidget(source_label); layout.addWidget(text, 1)
        self.rows.insertWidget(0, row)
        while self.rows.count() > 100:
            item = self.rows.takeAt(self.rows.count() - 1)
            if item.widget(): item.widget().deleteLater()

    def clear(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget(): item.widget().deleteLater()


class NeuroGoruWindow(QMainWindow):
    NAVIGATION = [("Dashboard", "⌂"), ("GPS Map", "⌖"), ("Alerts", "!"), ("History", "◷"), ("About", "ⓘ")]

    def __init__(self) -> None:
        super().__init__(); self.setWindowTitle("NeuroGoru • Smart Livestock Monitoring"); self.resize(1360, 860); self.setMinimumSize(1050, 680); self.setStyleSheet(stylesheet())
        self.last_fence = (23.8376, 90.3576, 250.0)
        self.last_fence_shape = "circle"
        self.last_fence_state = None
        self.temperature_abnormal = False
        self.last_gps_satellite_count: int | None = None
        self.last_valid_gps_data: dict | None = None
        self.selected_goru = 0
        self.current_navigation = 0
        self._build_ui()
        host = os.environ.get("NEUROGORU_ESP32_HOST", "192.168.4.1")
        try: port = int(os.environ.get("NEUROGORU_ESP32_PORT", "5010"))
        except ValueError: port = 5010
        self.status_log.add(f"Connecting to ESP32 at {host}:{port}", "Info", "ESP32")
        self.esp32 = Esp32Client(host, port, self)
        self.esp32.status_changed.connect(self._status_changed); self.esp32.message_received.connect(self._message); self.esp32.start()

    def _build_ui(self) -> None:
        root = BackgroundWidget(Path(__file__).resolve().parent / "assets" / "cow-pasture-background.png"); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        top = QFrame(objectName="topbar"); top.setFixedHeight(72); top_l = QHBoxLayout(top)
        logo = QLabel("NG"); logo.setAlignment(Qt.AlignmentFlag.AlignCenter); logo.setFixedSize(42,42); logo.setStyleSheet(f"background:{ACCENT};color:#062016;border-radius:13px;font-weight:900")
        top_l.addWidget(logo); top_l.addWidget(QLabel("NeuroGoru")); top_l.addStretch(); self.esp_status = QLabel("ESP32 • CONNECTING"); top_l.addWidget(self.esp_status); self.clock = QLabel(); top_l.addWidget(self.clock)
        outer.addWidget(top)
        body = QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)
        side = QFrame(objectName="sidebar"); side.setFixedWidth(210); side_l = QVBoxLayout(side); self.nav_buttons=[]
        cattle_title = QLabel("SELECT CATTLE")
        cattle_title.setStyleSheet("color:#8fa3bc;font-size:10px;font-weight:900;padding:6px 8px")
        side_l.addWidget(cattle_title)
        self.goru_buttons = []
        for i, label in enumerate(("Goru 1  •  Collar", "Goru 2  •  No collar")):
            button = QPushButton(label, objectName="nav")
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, n=i: self._select_goru(n))
            side_l.addWidget(button)
            self.goru_buttons.append(button)
        self.goru_buttons[0].setChecked(True)
        section = QLabel("MONITORING")
        section.setStyleSheet("color:#8fa3bc;font-size:10px;font-weight:900;padding:12px 8px 4px")
        side_l.addWidget(section)
        for i,(name,icon) in enumerate(self.NAVIGATION):
            button=QPushButton(f"{icon}    {name}", objectName="nav"); button.setCheckable(True); button.clicked.connect(lambda _=False,n=i:self._navigate(n)); side_l.addWidget(button); self.nav_buttons.append(button)
        self.nav_buttons[0].setChecked(True); side_l.addStretch(); body.addWidget(side)
        self.stack=QStackedWidget(); self.dashboard=DashboardPage(); self.gps=MapPage(); self.alerts=AlertsPage(); self.history=HistoryPage(); self.about=AboutPage()
        for page in [self.dashboard,self.gps,self.alerts,self.history,self.about]:
            page.setContentsMargins(12, 8, 12, 8)
            self.stack.addWidget(page)
        self.no_collar_page = QWidget()
        no_collar_layout = QVBoxLayout(self.no_collar_page)
        no_collar_layout.addStretch()
        no_collar_title = QLabel("Goru 2")
        no_collar_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_collar_title.setStyleSheet("font-size:30px;font-weight:900;color:#ffffff")
        no_collar_message = QLabel("No collar assigned\nTelemetry will appear here after a collar is connected.")
        no_collar_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_collar_message.setStyleSheet("font-size:16px;color:#8fa3bc")
        no_collar_layout.addWidget(no_collar_title)
        no_collar_layout.addWidget(no_collar_message)
        no_collar_layout.addStretch()
        self.stack.addWidget(self.no_collar_page)
        body.addWidget(self.stack,1); outer.addLayout(body,1)
        self.status_log = StatusLog(); outer.addWidget(self.status_log)
        self.dashboard.fence_submitted.connect(self._set_fence)
        self.dashboard.fence_previewed.connect(self._preview_dashboard_fence)
        self.gps.fence_submitted.connect(self._set_map_fence)
        self.gps.fence_previewed.connect(self._preview_fence)
        self.gps.demo_cow_submitted.connect(self._set_demo_cow_position)
        self.gps.demo_reset_requested.connect(self._clear_demo_cow_position)
        self.gps.set_fence(*self.last_fence)
        timer=QTimer(self); timer.timeout.connect(lambda:self.clock.setText(datetime.now().strftime("%d %b %Y  •  %I:%M:%S %p"))); timer.start(1000); timer.timeout.emit(); self._clock_timer=timer

    def _navigate(self,index:int)->None:
        self.current_navigation = index
        self.stack.setCurrentIndex(index if self.selected_goru == 0 else 5)
        for i,b in enumerate(self.nav_buttons): b.setChecked(i==index)

    def _select_goru(self, index: int) -> None:
        self.selected_goru = index
        for i, button in enumerate(self.goru_buttons):
            button.setChecked(i == index)
        self.stack.setCurrentIndex(self.current_navigation if index == 0 else 5)
        if index == 0:
            self.status_log.add("Goru 1 selected — collar telemetry active", "Success", "Cattle")
        else:
            self.status_log.add("Goru 2 selected — no collar or telemetry assigned", "Info", "Cattle")

    @staticmethod
    def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        value = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        return 6_371_000.0 * 2.0 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1.0 - value)))

    def _status_changed(self,online:bool,detail:str)->None:
        self.dashboard.set_device_status("esp32", online)
        self.esp_status.setText(f"ESP32 • {'ONLINE' if online else 'OFFLINE'}")
        color = '#32d583' if online else '#f04438'
        background = '#0c3026' if online else '#35171c'
        self.esp_status.setStyleSheet(f"color:{color};background:{background};border:2px solid {color};border-radius:13px;padding:10px 18px;font-weight:900;font-size:12px")
        if online:
            self.status_log.add(f"ESP32 connected successfully — {detail}", "Success", "ESP32")
        else:
            self._add_alert("System", f"ESP32 disconnected: {detail}", "Warning")

    def _set_fence(self,lat:float,lon:float,radius:float)->None:
        self.last_fence=(lat,lon,radius)
        self.gps.set_fence(lat,lon,radius)
        self.dashboard.set_fence_inputs(lat,lon,radius)
        sent=self.esp32.set_fence(lat,lon,radius,self.last_fence_shape)
        self.dashboard.set_fence_feedback("Fence sent to ESP32." if sent else "Fence saved locally; ESP32 is offline.", sent)
        self.status_log.add(f"Fence: {lat:.8f}, {lon:.8f}, radius {radius:.0f} m", "Success" if sent else "Warning", "Fence")

    def _set_map_fence(self, lat: float, lon: float, radius: float, shape: str) -> None:
        self.last_fence_shape = shape.lower()
        self._set_fence(lat, lon, radius)

    def _preview_fence(self,lat:float,lon:float,radius:float)->None:
        self.dashboard.set_fence_inputs(lat,lon,radius)

    def _preview_dashboard_fence(self,lat:float,lon:float,radius:float)->None:
        self.gps.set_fence(lat,lon,radius)

    def _set_demo_cow_position(self, lat: float, lon: float) -> None:
        sent = self.esp32.set_demo_cow_position(lat, lon)
        self.status_log.add(
            f"Demo cow position: {lat:.8f}, {lon:.8f}",
            "Success" if sent else "Warning",
            "Geofence Demo",
        )

    def _clear_demo_cow_position(self) -> None:
        sent = self.esp32.clear_demo_cow_position()
        self.status_log.add(
            "Demo cow movement disabled; using real/last-known GPS position",
            "Success" if sent else "Warning",
            "Geofence Demo",
        )

    def _message(self,message:str)->None:
        if message.startswith("TELEMETRY:"):
            try: data=json.loads(message.split(":",1)[1])
            except (json.JSONDecodeError,ValueError): self._add_alert("System","Invalid telemetry packet received","Warning"); return
            aliases={"lat":"latitude","lon":"longitude","lng":"longitude","alt":"altitude","temp":"temperature","distance":"fence_distance","fenceDistance":"fence_distance","fenceStatus":"fence_status","accel_x":"acceleration_x","accel_y":"acceleration_y","accel_z":"acceleration_z","ax":"acceleration_x","ay":"acceleration_y","az":"acceleration_z","satellites":"gps_satellites","sats":"gps_satellites"}
            data={aliases.get(k,k):v for k,v in data.items()}; data["received_at"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # The ESP32 is the source of truth for the active fence. This keeps
            # map edits and manual radius updates synchronized after reconnects.
            if data.get("fence_set", False):
                try:
                    active_fence = (
                        float(data["fence_latitude"]),
                        float(data["fence_longitude"]),
                        float(data["fence_radius"]),
                    )
                    self.last_fence = active_fence
                    self.last_fence_shape = str(data.get("fence_shape", "circle")).lower()
                    self.dashboard.set_fence_inputs(*active_fence)
                    if not self.gps.map._editable:
                        self.gps.set_fence(*active_fence)
                        self.gps.set_fence_shape(self.last_fence_shape)
                except (KeyError, TypeError, ValueError):
                    pass
            if data.get("gps_fix_stored", False) and not data.get("gps_valid", False):
                data["position_cached"] = True
            if data.get("gps_valid", False):
                try:
                    if float(data["latitude"]) != 0.0 or float(data["longitude"]) != 0.0:
                        self.last_valid_gps_data = {
                            "latitude": float(data["latitude"]),
                            "longitude": float(data["longitude"]),
                            "altitude": float(data.get("altitude", 0.0)),
                        }
                except (KeyError, TypeError, ValueError):
                    pass
            elif not data.get("demo_position_active", False) and self.last_valid_gps_data:
                data.update(self.last_valid_gps_data)
                data["position_cached"] = True
            # Calculate geofence distance from the position actually shown by
            # the UI, so live and retained GPS positions behave consistently.
            try:
                latitude = float(data["latitude"])
                longitude = float(data["longitude"])
                has_displayed_position = latitude != 0.0 or longitude != 0.0
                if has_displayed_position:
                    fence_latitude, fence_longitude, fence_radius = self.last_fence
                    north = (latitude - fence_latitude) * 111_320.0
                    east = (longitude - fence_longitude) * 111_320.0 * math.cos(math.radians(fence_latitude))
                    radius = float(fence_radius)
                    shape = self.last_fence_shape
                    vertical_ratio = 0.70 if shape == "oval" else 0.65 if shape == "rectangle" else 1.0
                    x = abs(east) / max(0.1, radius)
                    y = abs(north) / max(0.1, radius * vertical_ratio)
                    normalized = max(x, y) if shape in {"square", "rectangle"} else math.hypot(x, y)
                    boundary_distance = (1.0 - normalized) * radius
                    data["fence_distance"] = round(boundary_distance, 1)
                    data["fence_status"] = "inside" if boundary_distance >= 0.0 else "outside"
            except (KeyError, TypeError, ValueError):
                pass
            try:
                satellite_count = max(0, int(data.get("gps_satellites", 0)))
            except (TypeError, ValueError):
                satellite_count = 0
            previous_satellites = self.last_gps_satellite_count
            if satellite_count > 0 and satellite_count != previous_satellites:
                self.status_log.add(
                    f"GPS satellites detected: {satellite_count}", "Success", "GPS"
                )
            elif satellite_count == 0 and previous_satellites is not None and previous_satellites > 0:
                self.status_log.add("GPS satellite signal lost: 0 detected", "Warning", "GPS")
            self.last_gps_satellite_count = satellite_count
            self.dashboard.update_telemetry(data); self.gps.update_telemetry(data); self.history.add_telemetry(data)
            state=str(data.get("fence_status","")).lower()
            if state=="outside" and self.last_fence_state!="outside": self._add_alert("Fence breach","Cattle moved outside the virtual fence","Critical")
            try:
                temperature = float(data["temperature"])
                abnormal = temperature >= 40.0
                if abnormal and not self.temperature_abnormal:
                    self._add_alert("Temperature", f"Abnormal temperature: {temperature:.1f}°C", "Warning")
                elif not abnormal and self.temperature_abnormal:
                    self.status_log.add(f"Temperature returned to normal: {temperature:.1f}°C", "Success", "DS18B20")
                self.temperature_abnormal = abnormal
            except (KeyError, TypeError, ValueError):
                pass
            self.last_fence_state=state
        elif message.startswith("ALERT:FALL_DEMO:"):
            alert_message = message.split(":", 2)[2]
            self._add_alert("Fall Detection", alert_message, "Critical")
            QApplication.beep()
            QTimer.singleShot(180, QApplication.beep)
            QTimer.singleShot(360, QApplication.beep)
            QMessageBox.critical(
                self,
                "EMERGENCY FALL ALERT",
                f"{alert_message}\n\nDetected from a low-gravity/impact movement sequence.",
            )
        elif message.startswith("ALERT:"): self._add_alert("ESP32",message.split(":",1)[1],"Critical")
        elif message == "STATUS:DS18B20:ONLINE":
            self.dashboard.set_device_status("ds18b20", True)
            self.status_log.add("DS18B20 temperature sensor connected", "Success", "DS18B20")
        elif message == "ERROR:DS18B20:DISCONNECTED":
            self.dashboard.set_device_status("ds18b20", False)
            self._add_alert("DS18B20", "Temperature sensor disconnected or reading invalid", "Warning")
        elif message == "STATUS:MPU6050:ONLINE":
            self.dashboard.set_device_status("mpu6050", True)
            self.status_log.add("MPU6050 motion sensor connected", "Success", "MPU6050")
        elif message == "ERROR:MPU6050:DISCONNECTED":
            self.dashboard.set_device_status("mpu6050", False)
            self._add_alert("MPU6050", "Motion sensor disconnected or reading invalid", "Warning")
        elif message == "STATUS:GPS:ONLINE":
            self.dashboard.set_device_status("gps", True)
            self.status_log.add("NEO-6M GPS sensor connected", "Success", "GPS")
        elif message == "ERROR:GPS:DISCONNECTED":
            self.dashboard.set_device_status("gps", False)
            self.last_gps_satellite_count = None
            self._add_alert("GPS", "GPS sensor disconnected or not sending data", "Warning")
        elif message.startswith("ACK:FENCE"):
            self.dashboard.set_fence_feedback("ESP32 confirmed the fence update.",True)
            self.status_log.add("ESP32 confirmed the virtual fence update", "Success", "Fence")

    def _add_alert(self,kind:str,message:str,severity:str)->None:
        alert={"time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"type":kind,"message":message,"severity":severity}; self.alerts.add_alert(alert); self.history.add_alert(alert)
        self.status_log.add(message, severity, kind)

    def closeEvent(self,event)->None:
        self.esp32.stop(); super().closeEvent(event)
