from __future__ import annotations

import math
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
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
        self.fence_shape = "circle"
        self._dragging_fence = False
        self._drag_meters_per_pixel = 1.0
        self._moving_fence = False
        self._move_start_point = QPointF()
        self._move_start_fence: tuple[float, float, float] | None = None
        self._editable = False
        self._fence_center_px = QPointF()
        self._radius_px = 0.0
        self._meters_per_pixel = 1.0
        self._origin: tuple[float, float] | None = None
        self._cattle_point: QPointF | None = None
        self._demo_cow_position: tuple[float, float] | None = None
        self._cow_origin: tuple[float, float] | None = None
        self._cow_editable = False
        self._dragging_cow = False
        self._trail: deque[tuple[float, float]] = deque(maxlen=80)

    def set_telemetry(self, data: dict) -> None:
        self.telemetry = dict(data)
        if data.get("gps_valid", False) and not data.get("demo_position_active", False):
            try:
                position = (float(data["latitude"]), float(data["longitude"]))
                if (position[0] != 0.0 or position[1] != 0.0) and (
                    not self._trail or self._distance_meters(self._trail[-1], position) >= 1.0
                ):
                    self._trail.append(position)
            except (KeyError, TypeError, ValueError):
                pass
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
        if self._cow_origin is None:
            self._cow_origin = (latitude, longitude)
        self.fence = (latitude, longitude, radius)
        self.update()

    def set_fence_shape(self, shape: str) -> None:
        normalized = shape.strip().lower()
        if normalized in {"circle", "oval", "square", "rectangle"}:
            self.fence_shape = normalized
            self.update()

    def _vertical_ratio(self) -> float:
        return 0.70 if self.fence_shape == "oval" else 0.65 if self.fence_shape == "rectangle" else 1.0

    def _normalized_geo_distance(self, position: tuple[float, float]) -> float:
        if not self.fence:
            return 0.0
        center_lat, center_lon, radius = self.fence
        north = (position[0] - center_lat) * 111_320.0
        east = (position[1] - center_lon) * 111_320.0 * math.cos(math.radians(center_lat))
        x = abs(east) / max(0.1, radius)
        y = abs(north) / max(0.1, radius * self._vertical_ratio())
        return max(x, y) if self.fence_shape in {"square", "rectangle"} else math.hypot(x, y)

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self._dragging_fence = False
        self._moving_fence = False
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
            return self._cow_origin
        try:
            return float(self.telemetry["latitude"]), float(self.telemetry["longitude"])
        except (KeyError, TypeError, ValueError):
            return self._cow_origin

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

        # Map furniture keeps the offline view readable without internet tiles.
        painter.setPen(QPen(QColor("#37516a"), 1))
        painter.drawLine(self.width() - 42, 54, self.width() - 42, 18)
        painter.drawLine(self.width() - 47, 25, self.width() - 42, 18)
        painter.drawLine(self.width() - 37, 25, self.width() - 42, 18)
        painter.setPen(QColor("#b8cbe0"))
        painter.drawText(self.width() - 47, 68, "N")

        cattle = self._gps_position()
        if not self._dragging_fence and not self._moving_fence and not self._dragging_cow:
            if cattle and self.fence:
                self._origin = (
                    (cattle[0] + self.fence[0]) / 2.0,
                    (cattle[1] + self.fence[1]) / 2.0,
                )
            else:
                self._origin = cattle or (self.fence[:2] if self.fence else None)
        if self.fence:
            # Use a perceptual scale so changing the configured radius visibly
            # grows/shrinks the circle without making large fences unusable.
            max_radius_px = max(70.0, min(self.width(), self.height()) * 0.42)
            desired_radius_px = min(max_radius_px, 28.0 + 4.0 * math.sqrt(max(1.0, self.fence[2])))
            self._meters_per_pixel = max(0.1, self.fence[2] / desired_radius_px)
            if cattle:
                separation = self._distance_meters(cattle, (self.fence[0], self.fence[1]))
                available_span_px = max(100.0, min(self.width() * 0.78, self.height() * 0.72))
                self._meters_per_pixel = max(
                    self._meters_per_pixel,
                    (separation + 2.0 * self.fence[2]) / available_span_px,
                )
            self._radius_px = max(8.0, self.fence[2] / self._meters_per_pixel)
            self._fence_center_px = self._geo_to_point(self.fence[0], self.fence[1])
            if cattle:
                cow_inside_fence = self._normalized_geo_distance(cattle) <= 1.0
                fence_state = "inside" if cow_inside_fence else "outside"
            else:
                fence_state = "waiting"
            fence_color = QColor(DANGER) if fence_state == "outside" else QColor(ACCENT)
            painter.setBrush(QColor(fence_color.red(), fence_color.green(), fence_color.blue(), 32))
            line_style = Qt.PenStyle.DashLine if self._editable else Qt.PenStyle.SolidLine
            painter.setPen(QPen(fence_color, 3, line_style))
            vertical_radius = self._radius_px * self._vertical_ratio()
            boundary_rect = QRectF(
                self._fence_center_px.x() - self._radius_px,
                self._fence_center_px.y() - vertical_radius,
                self._radius_px * 2.0,
                vertical_radius * 2.0,
            )
            if self.fence_shape in {"square", "rectangle"}:
                painter.drawRect(boundary_rect)
            else:
                painter.drawEllipse(boundary_rect)

            if self._editable:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(ACCENT))
                handles = (
                    QPointF(self._fence_center_px.x() - self._radius_px, self._fence_center_px.y()),
                    QPointF(self._fence_center_px.x() + self._radius_px, self._fence_center_px.y()),
                    QPointF(self._fence_center_px.x(), self._fence_center_px.y() - vertical_radius),
                    QPointF(self._fence_center_px.x(), self._fence_center_px.y() + vertical_radius),
                )
                for handle in handles:
                    painter.drawEllipse(handle, 8, 8)

            painter.setPen(fence_color)
            mode = "EDIT MODE - resize edge or move shaded area" if self._editable else "LOCKED - click Edit Fence"
            painter.drawText(18, 28, f"{self.fence_shape.title()} fence: {self.fence[2]:.0f} m  •  {fence_state.upper()}  •  {mode}")

            # A scale bar reflects the current fence-derived map scale.
            scale_m = max(1, round(self._meters_per_pixel * 80))
            scale_px = scale_m / self._meters_per_pixel
            painter.setPen(QPen(QColor("#b8cbe0"), 2))
            y = self.height() - 22
            painter.drawLine(18, y, int(18 + scale_px), y)
            painter.drawLine(18, y - 4, 18, y + 4)
            painter.drawLine(int(18 + scale_px), y - 4, int(18 + scale_px), y + 4)
            painter.drawText(18, y - 7, f"{scale_m} m")

        if len(self._trail) > 1 and self._origin:
            trail_points = [self._geo_to_point(*position) for position in self._trail]
            painter.setPen(QPen(QColor(51, 190, 255, 150), 2, Qt.PenStyle.DashLine))
            for start, end in zip(trail_points, trail_points[1:]):
                painter.drawLine(start, end)

        if cattle:
            point = self._geo_to_point(*cattle)
            self._cattle_point = point

            if self.fence:
                inside = self._normalized_geo_distance(cattle) <= 1.0
                painter.setPen(QPen(QColor(ACCENT if inside else DANGER), 2, Qt.PenStyle.DashLine))
                painter.drawLine(point, self._fence_center_px)

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

        else:
            self._cattle_point = None
            painter.setPen(QColor("#8fa3bc"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for a valid GPS fix from ESP32")

    def _over_fence(self, point: QPointF) -> bool:
        if not self.fence:
            return False
        dx = point.x() - self._fence_center_px.x()
        dy = point.y() - self._fence_center_px.y()
        x = abs(dx) / max(1.0, self._radius_px)
        y = abs(dy) / max(1.0, self._radius_px * self._vertical_ratio())
        normalized = max(x, y) if self.fence_shape in {"square", "rectangle"} else math.hypot(x, y)
        return normalized <= 1.0

    def _near_fence_boundary(self, point: QPointF) -> bool:
        if not self.fence:
            return False
        dx = abs(point.x() - self._fence_center_px.x()) / max(1.0, self._radius_px)
        dy = abs(point.y() - self._fence_center_px.y()) / max(1.0, self._radius_px * self._vertical_ratio())
        normalized = max(dx, dy) if self.fence_shape in {"square", "rectangle"} else math.hypot(dx, dy)
        return abs(normalized - 1.0) * self._radius_px <= 12.0

    def _show_hover_details(self, event: QMouseEvent) -> None:
        point = event.position()
        cattle = self._gps_position()
        if cattle and self._cattle_point is not None and math.hypot(
            point.x() - self._cattle_point.x(), point.y() - self._cattle_point.y()
        ) <= 18.0:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"Latitude: {cattle[0]:.8f}\nLongitude: {cattle[1]:.8f}",
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
        if self._editable and event.button() == Qt.MouseButton.LeftButton and self._origin and self._near_fence_boundary(event.position()):
            self._dragging_fence = True
            self._drag_meters_per_pixel = self._meters_per_pixel
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self._editable and event.button() == Qt.MouseButton.LeftButton and self._origin and self._over_fence(event.position()):
            self._moving_fence = True
            self._move_start_point = event.position()
            self._move_start_fence = self.fence
            self._drag_meters_per_pixel = self._meters_per_pixel
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
            dx = abs(event.position().x() - self._fence_center_px.x())
            dy = abs(event.position().y() - self._fence_center_px.y()) / self._vertical_ratio()
            distance_px = max(dx, dy) if self.fence_shape in {"square", "rectangle"} else math.hypot(dx, dy)
            radius = min(100_000.0, max(1.0, distance_px * self._drag_meters_per_pixel))
            self.fence = (self.fence[0], self.fence[1], radius)
            self.fence_previewed.emit(*self.fence)
            self.update()
            event.accept()
            return
        if self._moving_fence and self._move_start_fence and self._origin:
            start_latitude, start_longitude, radius = self._move_start_fence
            east = (event.position().x() - self._move_start_point.x()) * self._drag_meters_per_pixel
            north = (self._move_start_point.y() - event.position().y()) * self._drag_meters_per_pixel
            latitude = start_latitude + north / 111_320.0
            cos_lat = max(0.01, abs(math.cos(math.radians(start_latitude))))
            longitude = start_longitude + east / (111_320.0 * cos_lat)
            self.fence = (latitude, longitude, radius)
            self.fence_previewed.emit(*self.fence)
            self.update()
            event.accept()
            return
        self._show_hover_details(event)
        over_cow = self._cattle_point is not None and math.hypot(
            event.position().x() - self._cattle_point.x(),
            event.position().y() - self._cattle_point.y(),
        ) <= 24.0
        over_boundary = self._editable and self._near_fence_boundary(event.position())
        over_area = self._editable and self._over_fence(event.position())
        can_drag = (self._cow_editable and over_cow) or over_boundary or over_area
        cursor = Qt.CursorShape.SizeAllCursor if over_area and not over_boundary else Qt.CursorShape.OpenHandCursor
        self.setCursor(cursor if can_drag else Qt.CursorShape.ArrowCursor)
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
        if event.button() == Qt.MouseButton.LeftButton and self._moving_fence and self.fence:
            self._moving_fence = False
            self._move_start_fence = None
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.fence_dropped.emit(*self.fence)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().leaveEvent(event)
