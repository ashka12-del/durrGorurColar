from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from mock_data.generator import MockDataGenerator
from pages.dashboard import DashboardPage
from pages.monitoring import MonitoringPage
from pages.sections import AboutPage, AlertsPage, AnalyticsPage, DeviceStatusPage, MapPage, SettingsPage
from styles.theme import ACCENT, stylesheet


class BackgroundWidget(QWidget):
    """Full-bleed image surface with a dark overlay for legible UI content."""

    def __init__(self, image_path: Path) -> None:
        super().__init__()
        self.setObjectName("root")
        self._background = QPixmap(str(image_path))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if not self._background.isNull():
            scaled = self._background.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            painter.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
        else:
            painter.fillRect(self.rect(), QColor("#08111f"))
        painter.fillRect(self.rect(), QColor(3, 10, 20, 122))
        super().paintEvent(event)


class NeuroGoruWindow(QMainWindow):
    NAVIGATION = [
        ("Dashboard", "▦"), ("Live Monitoring", "◉"), ("GPS Map", "⌖"),
        ("Virtual Fence", "⬡"), ("Alerts", "!"), ("Device Status", "◆"),
        ("Analytics", "⌁"), ("History", "◷"), ("Settings", "⚙"), ("About", "ⓘ"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NeuroGoru • Smart Livestock Monitoring")
        self.resize(1440, 900)
        self.setMinimumSize(1080, 700)
        self.setStyleSheet(stylesheet())
        self.generator = MockDataGenerator(self)
        self._build_ui()
        self.generator.updated.connect(self._update_data)
        self.generator.alert_created.connect(self.alerts.add_alert)
        self._update_data(self.generator.cows)

    def _build_ui(self) -> None:
        background_path = Path(__file__).resolve().parent / "assets" / "cow-pasture-background.png"
        root = BackgroundWidget(background_path)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._topbar())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        self.dashboard = DashboardPage()
        self.monitoring = MonitoringPage(self.generator.cows)
        self.gps = MapPage(self.generator.cows)
        self.fence = MapPage(self.generator.cows, True)
        self.alerts = AlertsPage()
        pages = [self.dashboard, self.monitoring, self.gps, self.fence, self.alerts, DeviceStatusPage(), AnalyticsPage(), AnalyticsPage("History"), SettingsPage(), AboutPage()]
        for page in pages:
            wrapper = QScrollArea()
            wrapper.setWidgetResizable(True)
            wrapper.setFrameShape(QFrame.Shape.NoFrame)
            page.setContentsMargins(22, 20, 22, 22)
            wrapper.setWidget(page)
            self.stack.addWidget(wrapper)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

    def _topbar(self) -> QFrame:
        bar = QFrame(objectName="topbar")
        bar.setFixedHeight(76)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(22, 0, 22, 0)
        logo = QLabel("NG")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(42, 42)
        logo.setStyleSheet(f"background:{ACCENT};color:#062016;border-radius:13px;font-weight:900;font-size:15px")
        layout.addWidget(logo)
        brand = QVBoxLayout()
        eyebrow = QLabel("SMART LIVESTOCK")
        eyebrow.setObjectName("eyebrow")
        name = QLabel("NeuroGoru")
        name.setObjectName("brand")
        brand.addWidget(eyebrow); brand.addWidget(name)
        layout.addLayout(brand)
        layout.addStretch()
        self.clock = QLabel()
        self.clock.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.clock)
        for symbol, tip in [("◉", "Notifications"), ("⚙", "Settings"), ("AN", "Profile")]:
            button = QPushButton(symbol)
            button.setObjectName("icon")
            button.setToolTip(tip)
            button.setFixedSize(42, 42)
            layout.addWidget(button)
        timer = QTimer(self)
        timer.timeout.connect(self._set_clock)
        timer.start(1000)
        self._clock_timer = timer
        self._set_clock()
        return bar

    def _sidebar(self) -> QFrame:
        side = QFrame(objectName="sidebar")
        side.setFixedWidth(224)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(12, 20, 12, 18)
        layout.setSpacing(5)
        section = QLabel("WORKSPACE")
        section.setStyleSheet("color:#60758e;font-size:10px;font-weight:800;padding:8px")
        layout.addWidget(section)
        self.nav_buttons = []
        for index, (name, icon) in enumerate(self.NAVIGATION):
            button = QPushButton(f"{icon}    {name}")
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, i=index: self._navigate(i))
            layout.addWidget(button)
            self.nav_buttons.append(button)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch()
        demo = QFrame(objectName="card")
        demo_layout = QVBoxLayout(demo)
        demo_layout.addWidget(QLabel("●  MOCK MODE"))
        note = QLabel("No hardware or backend connected")
        note.setWordWrap(True)
        note.setStyleSheet("color:#7f94ad;font-size:10px")
        demo_layout.addWidget(note)
        layout.addWidget(demo)
        return side

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def _set_clock(self) -> None:
        now = datetime.now()
        self.clock.setText(now.strftime("%A, %d %B\n%I:%M:%S %p"))

    def _update_data(self, cows: list) -> None:
        self.dashboard.update_cows(cows)
        self.monitoring.update_cows(cows)
        self.gps.update_cows(cows)
        self.fence.update_cows(cows)
