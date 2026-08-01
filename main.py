from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app import NeuroGoruWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuroGoru")
    app.setOrganizationName("NeuroGoru University Project")
    window = NeuroGoruWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

