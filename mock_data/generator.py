from __future__ import annotations

import random
from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, QTimer, Signal


@dataclass(frozen=True)
class Cow:
    cow_id: str
    name: str
    battery: int
    temperature: float
    activity: str
    gps: str
    fence: str
    health: str
    lat: float
    lon: float


class MockDataGenerator(QObject):
    updated = Signal(list)
    alert_created = Signal(dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cows = [
            Cow("NG-001", "Shorna", 92, 38.4, "Grazing", "Connected", "Inside", "Healthy", 23.8376, 90.3576),
            Cow("NG-002", "Maya", 74, 38.8, "Walking", "Connected", "Inside", "Healthy", 23.8390, 90.3604),
            Cow("NG-003", "Chandni", 39, 39.5, "Resting", "Connected", "Inside", "Warning", 23.8354, 90.3621),
            Cow("NG-004", "Lalmoni", 81, 38.6, "Walking", "Connected", "Inside", "Healthy", 23.8414, 90.3558),
            Cow("NG-005", "Rani", 18, 40.2, "Stationary", "Lost", "Outside", "Critical", 23.8430, 90.3640),
            Cow("NG-006", "Nandini", 66, 38.7, "Grazing", "Connected", "Inside", "Healthy", 23.8366, 90.3543),
        ]
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(2800)

    def _tick(self) -> None:
        next_cows: list[Cow] = []
        for cow in self.cows:
            battery = max(5, cow.battery - random.choice([0, 0, 0, 1]))
            temp = min(41.2, max(37.4, cow.temperature + random.uniform(-0.18, 0.18)))
            lat = cow.lat + random.uniform(-0.00025, 0.00025)
            lon = cow.lon + random.uniform(-0.00025, 0.00025)
            health = "Critical" if temp >= 40 or battery <= 15 else "Warning" if temp >= 39.3 or battery <= 35 else "Healthy"
            next_cows.append(replace(cow, battery=battery, temperature=temp, lat=lat, lon=lon, health=health))
        self.cows = next_cows
        self.updated.emit(self.cows)
        if random.random() < 0.16:
            cow = random.choice(self.cows)
            self.alert_created.emit({"cow": cow.name, "alert": random.choice(["Battery Low", "High Temperature", "Fence Crossed", "GPS Lost"]), "severity": cow.health})

