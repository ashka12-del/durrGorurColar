from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from styles.theme import ACCENT, DANGER, INFO, MUTED, WARNING


def shadow(widget: QWidget, blur: int = 28) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, 7)
    effect.setColor(QColor(0, 0, 0, 100))
    widget.setGraphicsEffect(effect)


class StatCard(QFrame):
    def __init__(self, title: str, value: str, icon: str, color: str = ACCENT, subtitle: str = "Live mock data") -> None:
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(126)
        shadow(self)
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        badge = QLabel(icon)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(38, 38)
        badge.setStyleSheet(f"background:{color}22;color:{color};border-radius:11px;font-size:19px")
        top.addWidget(badge)
        top.addStretch()
        pulse = QLabel("● LIVE")
        pulse.setStyleSheet(f"color:{color};font-size:10px;font-weight:700")
        top.addWidget(pulse)
        root.addLayout(top)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size:25px;font-weight:800")
        root.addWidget(self.value_label)
        label = QLabel(title)
        label.setStyleSheet(f"color:{MUTED};font-weight:600")
        root.addWidget(label)
        detail = QLabel(subtitle)
        detail.setStyleSheet("color:#60758e;font-size:10px")
        root.addWidget(detail)

    def set_value(self, value: str) -> None:
        if self.value_label.text() == value:
            return
        self.value_label.setText(value)
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(360)
        animation.setStartValue(0.55)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start()
        self._animation = animation


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("muted")
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)


class ActionButton(QPushButton):
    activated = Signal(str)

    def __init__(self, text: str, icon: str, danger: bool = False) -> None:
        super().__init__(f"{icon}  {text}")
        self.action_name = text
        self.setObjectName("danger" if danger else "primary")
        self.clicked.connect(lambda: self.activated.emit(self.action_name))


def health_color(status: str) -> str:
    return ACCENT if status == "Healthy" else WARNING if status == "Warning" else DANGER


STATUS_COLORS = {"Healthy": ACCENT, "Warning": WARNING, "Critical": DANGER, "Online": ACCENT, "Degraded": WARNING, "Offline": DANGER, "Info": INFO}

