from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from styles.theme import ACCENT, DANGER


class TelemetryMap(QWidget):
    """Offline local map with a live cattle marker and draggable circular fence."""

    fence_previewed = Signal(float, float, float)
    fence_dropped = Signal(float, float, float)
    cow_previewed = Signal(float, float)
    cow_dropped = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self.telemetry: dict = {}
        self.fence: tuple[float, float, float] | None = None
        self._dragging_fence = False
        self._editable = False
        self._fence_center_px = QPointF()
        self._radius_px = 0.0
        self._meters_per_pixel = 1.0
        self._origin: tuple[float, float] | None = None
        self._cattle_point: QPointF | None = None
        self._demo_cow_position: tuple[float, float] | None = None
        self._cow_editable = False
        self._dragging_cow = False

    def set_telemetry(self, data: dict) -> None:
        self.telemetry = dict(data)
        if data.get("demo_position_active", False):
            try:
                self._demo_cow_position = (float(data["latitude"]), float(data["longitude"]))
            except (KeyError, TypeError, ValueError):
                pass
        self.update()

    def set_cow_editable(self, editable: bool) -> bool:
        if editable and self._gps_position() is None:
            return False
        if editable and self._demo_cow_position is None:
            self._demo_cow_position = self._gps_position()
        self._cow_editable = editable
        self._dragging_cow = False
        self.update()
        return True

    def clear_demo_cow(self) -> None:
        self._demo_cow_position = None
        self._cow_editable = False
        self._dragging_cow = False
        self.update()

    def set_fence(self, latitude: float, longitude: float, radius: float) -> None:
        self.fence = (latitude, longitude, radius)
        self.update()

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self._dragging_fence = False
        self.unsetCursor()
        self.update()

    def _gps_position(self) -> tuple[float, float] | None:
        if self._demo_cow_position is not None:
            return self._demo_cow_position
        if not (
            self.telemetry.get("gps_valid", False)
            or self.telemetry.get("position_cached", False)
            or self.telemetry.get("position_valid", False)
        ):
            return None
        try:
            return float(self.telemetry["latitude"]), float(self.telemetry["longitude"])
        except (KeyError, TypeError, ValueError):
            return None

    def _geo_to_point(self, latitude: float, longitude: float) -> QPointF:
        if self._origin is None:
            return QPointF(self.width() / 2, self.height() / 2)
        origin_lat, origin_lon = self._origin
        north = (latitude - origin_lat) * 111_320.0
        east = (longitude - origin_lon) * 111_320.0 * math.cos(math.radians(origin_lat))
        return QPointF(
            self.width() / 2 + east / self._meters_per_pixel,
            self.height() / 2 - north / self._meters_per_pixel,
        )

    def _point_to_geo(self, point: QPointF) -> tuple[float, float]:
        assert self._origin is not None
        origin_lat, origin_lon = self._origin
        east = (point.x() - self.width() / 2) * self._meters_per_pixel
        north = (self.height() / 2 - point.y()) * self._meters_per_pixel
        latitude = origin_lat + north / 111_320.0
        cos_lat = max(0.01, abs(math.cos(math.radians(origin_lat))))
        longitude = origin_lon + east / (111_320.0 * cos_lat)
        return latitude, longitude

    @staticmethod
    def _distance_meters(start: tuple[float, float], end: tuple[float, float]) -> float:
        lat1, lon1 = map(math.radians, start)
        lat2, lon2 = map(math.radians, end)
        delta_lat = lat2 - lat1
        delta_lon = lon2 - lon1
        value = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        )
        return 6_371_000.0 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1.0 - value)))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1b2b"))
        painter.setPen(QPen(QColor("#1a3347"), 1))
        for x in range(0, self.width(), 42):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 42):
            painter.drawLine(0, y, self.width(), y)

        cattle = self._gps_position()
        if not self._dragging_fence and not self._dragging_cow:
            self._origin = cattle or (self.fence[:2] if self.fence else None)
        if self.fence:
            # Use a perceptual scale so changing the configured radius visibly
            # grows/shrinks the circle without making large fences unusable.
            max_radius_px = max(70.0, min(self.width(), self.height()) * 0.42)
            self._radius_px = min(max_radius_px, 28.0 + 4.0 * math.sqrt(max(1.0, self.fence[2])))
            self._meters_per_pixel = max(0.1, self.fence[2] / self._radius_px)
            self._fence_center_px = self._geo_to_point(self.fence[0], self.fence[1])
            painter.setBrush(QColor(50, 213, 131, 28))
            line_style = Qt.PenStyle.DashLine if self._editable else Qt.PenStyle.SolidLine
            painter.setPen(QPen(QColor(ACCENT), 3, line_style))
            painter.drawEllipse(self._fence_center_px, self._radius_px, self._radius_px)
            if self._editable:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(ACCENT))
                painter.drawEllipse(self._fence_center_px, 7, 7)
            painter.setPen(QColor(ACCENT))
            mode = "EDIT MODE - drag to reposition" if self._editable else "LOCKED - click Edit Fence to move"
            painter.drawText(18, 28, f"Virtual fence: {self.fence[2]:.0f} m  -  {mode}")

        if cattle:
            point = self._geo_to_point(*cattle)
            self._cattle_point = point

            # Draw red origin point for cow location (glow rings + solid red origin + white pinpoint center)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(240, 68, 56, 45))
            painter.drawEllipse(point, 24, 24)
            painter.setBrush(QColor(240, 68, 56, 110))
            painter.drawEllipse(point, 15, 15)
            painter.setBrush(QColor(DANGER))
            painter.drawEllipse(point, 8, 8)
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(point, 2.5, 2.5)

            # Draw cow location badge directly above the red origin point
            source = "DEMO" if self._demo_cow_position is not None else ("LAST GPS" if self.telemetry.get("position_cached") else "LIVE GPS")
            title_text = f"📍 COW ORIGIN [{source}]"
            coord_text = f"Lat: {cattle[0]:.8f}, Lon: {cattle[1]:.8f}"

            font = painter.font()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            w1 = fm.horizontalAdvance(title_text)
            w2 = fm.horizontalAdvance(coord_text)
            box_w = max(w1, w2) + 16
            box_h = 36
            box_x = int(point.x() - box_w / 2)
            box_y = int(point.y() - 22 - box_h)

            painter.setPen(QPen(QColor(DANGER), 1))
            painter.setBrush(QColor(13, 27, 43, 225))
            painter.drawRoundedRect(box_x, box_y, box_w, box_h, 6, 6)

            painter.setPen(QColor("#ffffff"))
            painter.drawText(box_x + (box_w - w1) // 2, box_y + 15, title_text)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor("#8fd3ff"))
            painter.drawText(box_x + (box_w - w2) // 2, box_y + 30, coord_text)
        else:
            self._cattle_point = None
            painter.setPen(QColor("#8fa3bc"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for a valid GPS fix from ESP32")

    def _over_fence(self, point: QPointF) -> bool:
        if not self.fence:
            return False
        dx = point.x() - self._fence_center_px.x()
        dy = point.y() - self._fence_center_px.y()
        return dx * dx + dy * dy <= self._radius_px * self._radius_px

    def _near_fence_boundary(self, point: QPointF) -> bool:
        if not self.fence:
            return False
        distance_px = math.hypot(point.x() - self._fence_center_px.x(), point.y() - self._fence_center_px.y())
        return abs(distance_px - self._radius_px) <= 12.0

    def _show_hover_details(self, event: QMouseEvent) -> None:
        point = event.position()
        cattle = self._gps_position()
        if cattle and self._cattle_point is not None and math.hypot(
            point.x() - self._cattle_point.x(), point.y() - self._cattle_point.y()
        ) <= 18.0:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"Cattle GPS Origin Location\nLatitude: {cattle[0]:.8f}\nLongitude: {cattle[1]:.8f}",
                self,
            )
            return
        if self.fence and self._origin and self._near_fence_boundary(point):
            boundary = self._point_to_geo(point)
            radius = self._distance_meters((self.fence[0], self.fence[1]), boundary)
            cattle_distance = self._distance_meters(cattle, boundary) if cattle else None
            detail = (
                f"Fence boundary point\nLatitude: {boundary[0]:.8f}\nLongitude: {boundary[1]:.8f}"
                f"\nRadius from fence center: {radius:.1f} m"
            )
            if cattle_distance is not None:
                detail += f"\nDistance from cattle: {cattle_distance:.1f} m"
            QToolTip.showText(event.globalPosition().toPoint(), detail, self)
            return
        QToolTip.hideText()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            self._cow_editable
            and event.button() == Qt.MouseButton.LeftButton
            and self._origin
            and self._cattle_point is not None
            and math.hypot(
                event.position().x() - self._cattle_point.x(),
                event.position().y() - self._cattle_point.y(),
            ) <= 24.0
        ):
            self._dragging_cow = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self._editable and event.button() == Qt.MouseButton.LeftButton and self._origin and self._over_fence(event.position()):
            self._dragging_fence = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging_cow and self._origin:
            latitude, longitude = self._point_to_geo(event.position())
            self._demo_cow_position = (latitude, longitude)
            self.cow_previewed.emit(latitude, longitude)
            self.update()
            event.accept()
            return
        if self._dragging_fence and self.fence and self._origin:
            latitude, longitude = self._point_to_geo(event.position())
            self.fence = (latitude, longitude, self.fence[2])
            self.fence_previewed.emit(*self.fence)
            self.update()
            event.accept()
            return
        self._show_hover_details(event)
        over_cow = self._cattle_point is not None and math.hypot(
            event.position().x() - self._cattle_point.x(),
            event.position().y() - self._cattle_point.y(),
        ) <= 24.0
        can_drag = (self._cow_editable and over_cow) or (self._editable and self._over_fence(event.position()))
        self.setCursor(Qt.CursorShape.OpenHandCursor if can_drag else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_cow and self._demo_cow_position:
            self._dragging_cow = False
            self._cow_editable = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.cow_dropped.emit(*self._demo_cow_position)
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_fence and self.fence:
            self._dragging_fence = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.fence_dropped.emit(*self.fence)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().leaveEvent(event)
