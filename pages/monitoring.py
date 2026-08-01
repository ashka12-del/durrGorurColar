from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget

from mock_data.generator import Cow
from styles.theme import MUTED
from widgets.common import ActionButton, PageHeader, health_color, shadow


class CowDetails(QDialog):
    def __init__(self, cow: Cow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{cow.name} • Live details")
        self.resize(720, 500)
        self.setModal(True)
        root = QVBoxLayout(self)
        hero = QHBoxLayout()
        avatar = QLabel("🐄")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(120, 120)
        avatar.setStyleSheet("font-size:56px;background:#173247;border-radius:24px")
        hero.addWidget(avatar)
        heading = QVBoxLayout()
        title = QLabel(cow.name)
        title.setStyleSheet("font-size:30px;font-weight:800")
        heading.addWidget(title)
        heading.addWidget(QLabel(f"{cow.cow_id}  •  Smart collar prototype"))
        badge = QLabel(cow.health)
        badge.setStyleSheet(f"color:{health_color(cow.health)};font-weight:800")
        heading.addWidget(badge)
        hero.addLayout(heading)
        hero.addStretch()
        root.addLayout(hero)
        grid = QGridLayout()
        values = [("Battery", f"{cow.battery}%"), ("Temperature", f"{cow.temperature:.1f}°C"), ("Coordinates", f"{cow.lat:.5f}, {cow.lon:.5f}"), ("Activity", cow.activity), ("Fence", cow.fence), ("Signal", "-67 dBm (mock)")]
        for i, (label, value) in enumerate(values):
            card = QFrame(objectName="card")
            box = QVBoxLayout(card)
            name = QLabel(label)
            name.setStyleSheet(f"color:{MUTED}")
            data = QLabel(value)
            data.setStyleSheet("font-size:18px;font-weight:700")
            box.addWidget(name)
            box.addWidget(data)
            grid.addWidget(card, i // 3, i % 3)
        root.addLayout(grid)
        buttons = QHBoxLayout()
        for label, icon, danger in [("Locate", "⌖", False), ("Ring Buzzer", "◉", False), ("Vibrate", "≈", False), ("Emergency Alert", "!", True)]:
            button = ActionButton(label, icon, danger)
            button.activated.connect(self._popup)
            buttons.addWidget(button)
        root.addLayout(buttons)

    def _popup(self, action: str) -> None:
        QMessageBox.information(self, "UI demonstration", f"{action} was clicked.\n\nThis is a frontend-only mock action; no command was sent.")


class CowCard(QFrame):
    def __init__(self, cow: Cow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cow = cow
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(220)
        shadow(self, 20)
        self.root = QVBoxLayout(self)
        self._render()

    def _render(self) -> None:
        while self.root.count():
            item = self.root.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        header = QHBoxLayout()
        avatar = QLabel("🐄")
        avatar.setStyleSheet("font-size:32px;background:#193149;border-radius:13px;padding:8px")
        header.addWidget(avatar)
        names = QVBoxLayout()
        title = QLabel(self.cow.name)
        title.setStyleSheet("font-size:17px;font-weight:800")
        names.addWidget(title)
        sub = QLabel(self.cow.cow_id)
        sub.setStyleSheet(f"color:{MUTED}")
        names.addWidget(sub)
        header.addLayout(names)
        header.addStretch()
        badge = QLabel(self.cow.health.upper())
        badge.setStyleSheet(f"color:{health_color(self.cow.health)};background:{health_color(self.cow.health)}20;border-radius:8px;padding:5px;font-size:10px;font-weight:800")
        header.addWidget(badge)
        self.root.addLayout(header)
        self.root.addSpacing(8)
        stats = [("Battery", f"{self.cow.battery}%"), ("Temp", f"{self.cow.temperature:.1f}°C"), ("Activity", self.cow.activity), ("GPS", self.cow.gps), ("Fence", self.cow.fence)]
        for label, value in stats:
            row = QHBoxLayout()
            key = QLabel(label); key.setStyleSheet(f"color:{MUTED}")
            val = QLabel(value); val.setStyleSheet("font-weight:700")
            row.addWidget(key); row.addStretch(); row.addWidget(val)
            self.root.addLayout(row)
        view = QPushButton("View details  →")
        view.setObjectName("primary")
        view.clicked.connect(lambda: CowDetails(self.cow, self).exec())
        self.root.addWidget(view)

    def update_cow(self, cow: Cow) -> None:
        self.cow = cow
        self._render()


class MonitoringPage(QWidget):
    def __init__(self, cows: list[Cow]) -> None:
        super().__init__()
        self.cards: dict[str, CowCard] = {}
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("Live monitoring", "Simulated collar telemetry refreshes every few seconds."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.grid = QGridLayout(content)
        self.grid.setSpacing(15)
        scroll.setWidget(content)
        root.addWidget(scroll)
        self.update_cows(cows)

    def update_cows(self, cows: list[Cow]) -> None:
        for index, cow in enumerate(cows):
            if cow.cow_id not in self.cards:
                self.cards[cow.cow_id] = CowCard(cow)
                self.grid.addWidget(self.cards[cow.cow_id], index // 3, index % 3)
            else:
                self.cards[cow.cow_id].update_cow(cow)

