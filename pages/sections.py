from __future__ import annotations

import random
from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from mock_data.generator import Cow
from pages.dashboard import TrendChart
from styles.theme import ACCENT, DANGER, INFO, MUTED, WARNING
from widgets.common import PageHeader, StatCard
from widgets.map_widget import MockMap


class MapPage(QWidget):
    def __init__(self, cows: list[Cow], fence_mode: bool = False) -> None:
        super().__init__()
        self.fence_mode = fence_mode
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("Virtual fence" if fence_mode else "GPS map", "Interactive simulated pasture view — drag to pan and scroll to zoom."))
        if fence_mode:
            stats = QHBoxLayout()
            stats.addWidget(StatCard("Fence area", "2.4 acres", "⬡", ACCENT, "Mock polygon"))
            stats.addWidget(StatCard("Cattle inside", "5", "✓", ACCENT, "Safe zone"))
            stats.addWidget(StatCard("Outside", "1", "!", DANGER, "Simulated breach"))
            root.addLayout(stats)
        self.map = MockMap()
        self.map.set_cows(cows)
        frame = QFrame(objectName="card")
        layout = QVBoxLayout(frame)
        layout.addWidget(self.map)
        root.addWidget(frame)

    def update_cows(self, cows: list[Cow]) -> None:
        self.map.set_cows(cows)


class AlertsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("Alerts", "Prioritized mock events from across the herd."))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Time", "Cow", "Alert", "Severity", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table)
        samples = [("Rani", "Fence Crossed", "Critical"), ("Chandni", "High Temperature", "Warning"), ("Rani", "GPS Lost", "Critical"), ("Shorna", "Battery Low", "Warning"), ("Maya", "SIM Offline", "Info")]
        for i, sample in enumerate(samples):
            self.add_alert({"cow": sample[0], "alert": sample[1], "severity": sample[2]}, datetime.now() - timedelta(minutes=i * 17))

    def add_alert(self, alert: dict, when: datetime | None = None) -> None:
        self.table.insertRow(0)
        values = [(when or datetime.now()).strftime("%I:%M %p"), alert["cow"], alert["alert"], alert["severity"], "New" if alert["severity"] == "Critical" else "Reviewed"]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column == 3:
                item.setForeground(QColor({"Critical": DANGER, "Warning": WARNING}.get(str(value), INFO)))
            self.table.setItem(0, column, item)


class DeviceStatusPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("Device status", "Visual mock states only — no hardware is queried."))
        grid = QGridLayout()
        devices = [("ESP32", "Online", "MCU"), ("GPS", "Online", "Satellite lock"), ("MPU6050", "Online", "Motion"), ("DS18B20", "Degraded", "Temperature"), ("SIM800L", "Offline", "Cellular"), ("Battery", "Online", "Power")]
        for i, (name, state, role) in enumerate(devices):
            color = ACCENT if state == "Online" else WARNING if state == "Degraded" else DANGER
            grid.addWidget(StatCard(name, state, "●", color, f"{role} • simulated"), i // 3, i % 3)
        root.addLayout(grid)
        root.addStretch()


class AnalyticsPage(QWidget):
    def __init__(self, title: str = "Analytics") -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader(title, "Generated datasets make trends feel realistic without storing any records."))
        grid = QGridLayout()
        for i, (name, color) in enumerate([("Battery trend", ACCENT), ("Temperature", WARNING), ("Movement", INFO), ("Alerts", DANGER)]):
            card = QFrame(objectName="card")
            layout = QVBoxLayout(card)
            label = QLabel(name); label.setStyleSheet("font-size:16px;font-weight:700")
            chart = TrendChart(color); chart.values = [random.randint(25, 92) for _ in range(12)]
            layout.addWidget(label); layout.addWidget(chart)
            grid.addWidget(card, i // 2, i % 2)
        root.addLayout(grid)


class SettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("Settings", "Frontend controls for demonstration; values are not persisted."))
        panel = QFrame(objectName="card")
        grid = QGridLayout(panel)
        controls = [("Dark mode", QCheckBox()), ("Notifications", QCheckBox()), ("Sound alerts", QCheckBox())]
        for i, (label, control) in enumerate(controls):
            control.setChecked(True)
            grid.addWidget(QLabel(label), i, 0); grid.addWidget(control, i, 1)
        language = QComboBox(); language.addItems(["English", "বাংলা"])
        refresh = QSpinBox(); refresh.setRange(1, 30); refresh.setValue(3); refresh.setSuffix(" seconds")
        theme = QComboBox(); theme.addItems(["Emerald", "Cyan", "Amber", "Violet"])
        for row, (label, control) in enumerate([("Language", language), ("Refresh rate", refresh), ("Theme color", theme)], start=3):
            grid.addWidget(QLabel(label), row, 0); grid.addWidget(control, row, 1)
        buttons = QHBoxLayout()
        save = QPushButton("Save preferences"); save.setObjectName("primary")
        reset = QPushButton("Reset")
        save.clicked.connect(lambda: QMessageBox.information(self, "UI demonstration", "Preferences previewed. Nothing was saved to a database."))
        buttons.addWidget(save); buttons.addWidget(reset); buttons.addStretch()
        grid.addLayout(buttons, 6, 0, 1, 2)
        root.addWidget(panel)
        root.addStretch()


class AboutPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("About", "A university prototype focused on thoughtful livestock-monitoring experiences."))
        card = QFrame(objectName="card")
        layout = QVBoxLayout(card)
        logo = QLabel("NG")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(82, 82)
        logo.setStyleSheet(f"font-size:25px;font-weight:900;color:#062016;background:{ACCENT};border-radius:22px")
        layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        title = QLabel("NeuroGoru")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:30px;font-weight:850")
        layout.addWidget(title)
        description = QLabel("Smart Virtual Fence & Livestock Monitoring System\n\nFrontend-only demonstration built with Python and PySide6. All cattle, locations, alerts, devices and analytics are simulated.\n\nUniversity: [University Name]\nTeam: [Team member placeholders]\nVersion 1.0.0 • Academic Prototype License")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        description.setStyleSheet(f"color:{MUTED};font-size:14px")
        layout.addWidget(description)
        root.addWidget(card)
        root.addStretch()
