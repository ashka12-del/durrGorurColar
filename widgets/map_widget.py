from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from mock_data.generator import Cow
from styles.theme import ACCENT, DANGER


class MockMap(QWidget):
    marker_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(430)
        self.cows: list[Cow] = []
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.drag_start: QPointF | None = None

    def set_cows(self, cows: list[Cow]) -> None:
        self.cows = cows
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.zoom = max(0.75, min(2.3, self.zoom + (0.12 if event.angleDelta().y() > 0 else -0.12)))
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.drag_start = event.position()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.drag_start:
            self.pan += event.position() - self.drag_start
            self.drag_start = event.position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.drag_start = None

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1b2b"))
        painter.save()
        painter.translate(self.width() / 2 + self.pan.x(), self.height() / 2 + self.pan.y())
        painter.scale(self.zoom, self.zoom)
        painter.translate(-self.width() / 2, -self.height() / 2)
        painter.setPen(QPen(QColor("#1a3347"), 1))
        for x in range(-100, self.width() + 100, 42):
            painter.drawLine(x, -100, x, self.height() + 100)
        for y in range(-100, self.height() + 100, 42):
            painter.drawLine(-100, y, self.width() + 100, y)
        road_pen = QPen(QColor("#29435a"), 15, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(road_pen)
        painter.drawLine(-40, int(self.height() * .72), self.width() + 50, int(self.height() * .24))
        painter.drawLine(int(self.width() * .25), -40, int(self.width() * .68), self.height() + 30)
        fence = QPainterPath()
        fence.moveTo(self.width() * .22, self.height() * .25)
        fence.lineTo(self.width() * .72, self.height() * .18)
        fence.lineTo(self.width() * .80, self.height() * .68)
        fence.lineTo(self.width() * .34, self.height() * .79)
        fence.closeSubpath()
        painter.setBrush(QColor(50, 213, 131, 18))
        painter.setPen(QPen(QColor(ACCENT), 2, Qt.PenStyle.DashLine))
        painter.drawPath(fence)
        for index, cow in enumerate(self.cows):
            x = self.width() * (.3 + (index % 3) * .19) + ((cow.lon * 10000) % 17)
            y = self.height() * (.34 + (index // 3) * .25) + ((cow.lat * 10000) % 13)
            color = QColor(DANGER if cow.fence == "Outside" or cow.health == "Critical" else ACCENT)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 45))
            painter.drawEllipse(QPointF(x, y), 17, 17)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), 7, 7)
            painter.setPen(QColor("#dce8f5"))
            painter.drawText(int(x + 12), int(y + 5), cow.name)
        painter.restore()
        painter.setPen(QColor("#9bb0c8"))
        painter.drawText(18, 26, "Mock map • Scroll to zoom • Drag to pan")

