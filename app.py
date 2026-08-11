from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

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
        self.last_fence_state = None
        self.temperature_abnormal = False
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
        for i,(name,icon) in enumerate(self.NAVIGATION):
            button=QPushButton(f"{icon}    {name}", objectName="nav"); button.setCheckable(True); button.clicked.connect(lambda _=False,n=i:self._navigate(n)); side_l.addWidget(button); self.nav_buttons.append(button)
        self.nav_buttons[0].setChecked(True); side_l.addStretch(); body.addWidget(side)
        self.stack=QStackedWidget(); self.dashboard=DashboardPage(); self.gps=MapPage(); self.alerts=AlertsPage(); self.history=HistoryPage(); self.about=AboutPage()
        for page in [self.dashboard,self.gps,self.alerts,self.history,self.about]:
            page.setContentsMargins(12, 8, 12, 8)
            self.stack.addWidget(page)
        body.addWidget(self.stack,1); outer.addLayout(body,1)
        self.status_log = StatusLog(); outer.addWidget(self.status_log)
        self.dashboard.fence_submitted.connect(self._set_fence)
        self.dashboard.fence_previewed.connect(self._preview_dashboard_fence)
        self.gps.fence_submitted.connect(self._set_fence)
        self.gps.fence_previewed.connect(self._preview_fence)
        self.gps.set_fence(*self.last_fence)
        timer=QTimer(self); timer.timeout.connect(lambda:self.clock.setText(datetime.now().strftime("%d %b %Y  •  %I:%M:%S %p"))); timer.start(1000); timer.timeout.emit(); self._clock_timer=timer

    def _navigate(self,index:int)->None:
        self.stack.setCurrentIndex(index)
        for i,b in enumerate(self.nav_buttons): b.setChecked(i==index)

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
        sent=self.esp32.set_fence(lat,lon,radius)
        self.dashboard.set_fence_feedback("Fence sent to ESP32." if sent else "Fence saved locally; ESP32 is offline.", sent)
        self.status_log.add(f"Fence: {lat:.6f}, {lon:.6f}, radius {radius:.0f} m", "Success" if sent else "Warning", "Fence")

    def _preview_fence(self,lat:float,lon:float,radius:float)->None:
        self.dashboard.set_fence_inputs(lat,lon,radius)

    def _preview_dashboard_fence(self,lat:float,lon:float,radius:float)->None:
        self.gps.set_fence(lat,lon,radius)

    def _message(self,message:str)->None:
        if message.startswith("TELEMETRY:"):
            try: data=json.loads(message.split(":",1)[1])
            except (json.JSONDecodeError,ValueError): self._add_alert("System","Invalid telemetry packet received","Warning"); return
            aliases={"lat":"latitude","lon":"longitude","lng":"longitude","alt":"altitude","temp":"temperature","distance":"fence_distance","fenceDistance":"fence_distance","fenceStatus":"fence_status","accel_x":"acceleration_x","accel_y":"acceleration_y","accel_z":"acceleration_z","ax":"acceleration_x","ay":"acceleration_y","az":"acceleration_z"}
            data={aliases.get(k,k):v for k,v in data.items()}; data["received_at"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            self._add_alert("GPS", "GPS sensor disconnected or not sending data", "Warning")
        elif message.startswith("ACK:FENCE"):
            self.dashboard.set_fence_feedback("ESP32 confirmed the fence update.",True)
            self.status_log.add("ESP32 confirmed the virtual fence update", "Success", "Fence")

    def _add_alert(self,kind:str,message:str,severity:str)->None:
        alert={"time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"type":kind,"message":message,"severity":severity}; self.alerts.add_alert(alert); self.history.add_alert(alert)
        self.status_log.add(message, severity, kind)

    def closeEvent(self,event)->None:
        self.esp32.stop(); super().closeEvent(event)
