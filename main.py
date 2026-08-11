from __future__ import annotations

import sys

from PySide6.QtCore import QLockFile, QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox

from app import NeuroGoruWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroGoru")
    app.setOrganizationName("NeuroGoru University Project")
    lock_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation) + "/neurogoru-ui.lock"
    instance_lock = QLockFile(lock_path)
    if not instance_lock.tryLock(100):
        QMessageBox.information(
            None,
            "NeuroGoru is already running",
            "Only one NeuroGoru dashboard can connect to the ESP32 at a time.\n\n"
            "Close the existing NeuroGoru window before starting another one.",
        )
        return 0
    window = NeuroGoruWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
