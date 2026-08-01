from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from mock_data.generator import Cow
from styles.theme import ACCENT, DANGER, INFO, MUTED, WARNING
from widgets.common import PageHeader, StatCard


class TrendChart(QWidget):
    def __init__(self, color: str = ACCENT) -> None:
        super().__init__()
        self.color = QColor(color)
        self.values = [44, 51, 48, 62, 57, 69, 65, 76, 71, 82, 78, 88]
        self.setMinimumHeight(210)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#22364e"), 1))
        for row in range(5):
            y = 20 + row * ((self.height() - 40) / 4)
            painter.drawLine(18, int(y), self.width() - 18, int(y))
        points = []
        for i, value in enumerate(self.values):
            x = 20 + i * ((self.width() - 40) / (len(self.values) - 1))
            y = self.height() - 20 - value * ((self.height() - 55) / 100)
            points.append((x, y))
        painter.setPen(QPen(self.color, 3))
        for i in range(len(points) - 1):
            painter.drawLine(QPointF(*points[i]), QPointF(*points[i + 1]))
        painter.setBrush(self.color)
        painter.setPen(Qt.PenStyle.NoPen)
        for x, y in points:
            painter.drawEllipse(QPointF(x, y), 4, 4)


from PySide6.QtCore import QPointF


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.addWidget(PageHeader("Dashboard", "A calm, real-time overview of your herd — powered entirely by mock data."))
        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards = {
            "total": StatCard("Total cattle", "6", "♞", INFO, "Registered collars"),
            "healthy": StatCard("Healthy", "4", "♥", ACCENT, "Within normal range"),
            "warning": StatCard("Needs attention", "1", "!", WARNING, "Review recommended"),
            "offline": StatCard("Critical / offline", "1", "×", DANGER, "Immediate attention"),
            "battery": StatCard("Average battery", "62%", "⌁", ACCENT, "Across all collars"),
            "temperature": StatCard("Average temperature", "39.0°C", "⌁", WARNING, "Livestock body temp"),
            "gps": StatCard("GPS connected", "5/6", "⌖", INFO, "Simulated signals"),
        }
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, i // 4, i % 4)
        root.addLayout(grid)
        lower = QHBoxLayout()
        chart_card = QFrame(objectName="card")
        chart_layout = QVBoxLayout(chart_card)
        title = QLabel("Herd activity trend")
        title.setStyleSheet("font-size:16px;font-weight:700")
        chart_layout.addWidget(title)
        chart_layout.addWidget(TrendChart())
        lower.addWidget(chart_card, 2)
        insight = QFrame(objectName="card")
        insight_layout = QVBoxLayout(insight)
        insight_layout.addWidget(QLabel("Live insight"))
        big = QLabel("83%")
        big.setStyleSheet(f"font-size:42px;font-weight:800;color:{ACCENT}")
        insight_layout.addWidget(big)
        detail = QLabel("of the herd is safely inside the virtual fence. One simulated collar needs attention.")
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color:{MUTED};line-height:1.5")
        insight_layout.addWidget(detail)
        insight_layout.addStretch()
        lower.addWidget(insight, 1)
        root.addLayout(lower)

    def update_cows(self, cows: list[Cow]) -> None:
        healthy = sum(c.health == "Healthy" for c in cows)
        warning = sum(c.health == "Warning" for c in cows)
        critical = sum(c.health == "Critical" for c in cows)
        self.cards["total"].set_value(str(len(cows)))
        self.cards["healthy"].set_value(str(healthy))
        self.cards["warning"].set_value(str(warning))
        self.cards["offline"].set_value(str(critical))
        self.cards["battery"].set_value(f"{sum(c.battery for c in cows) // len(cows)}%")
        self.cards["temperature"].set_value(f"{sum(c.temperature for c in cows) / len(cows):.1f}°C")
        self.cards["gps"].set_value(f"{sum(c.gps == 'Connected' for c in cows)}/{len(cows)}")

