from __future__ import annotations

ACCENT = "#32d583"
BG = "#08111f"
SURFACE = "#101c2d"
SURFACE_2 = "#17253a"
TEXT = "#f2f6fc"
MUTED = "#8fa3bc"
WARNING = "#fdb022"
DANGER = "#f04438"
INFO = "#36bffa"


def stylesheet() -> str:
    return f"""
    * {{ font-family: 'Segoe UI', 'Inter', sans-serif; color: {TEXT}; }}
    QMainWindow, QWidget#root {{ background: transparent; }}
    QAbstractScrollArea {{ background: transparent; border: none; }}
    QAbstractScrollArea > QWidget > QWidget {{ background: transparent; }}
    QFrame#topbar, QFrame#sidebar {{ background: rgba(8, 17, 31, 226); border: none; }}
    QFrame#espStatus {{ background:#2a2613; border:1px solid {WARNING}; border-radius:12px; }}
    QFrame#espStatus[online="true"] {{ background:#102d26; border:1px solid {ACCENT}; }}
    QFrame#espStatus QLabel {{ color:#f5c94c; font-size:11px; font-weight:800; }}
    QFrame#espStatus[online="true"] QLabel {{ color:{ACCENT}; }}
    QFrame#eventRegistry {{ background:rgba(8,17,31,242); border-top:1px solid #29445f; }}
    QFrame#statusLog {{ background:rgba(5,13,24,248); border-top:2px solid #29445f; }}
    QFrame#logRow {{ background:#101d2e; border:1px solid #223b55; border-radius:7px; }}
    QLabel#logTitle {{ color:white; font-size:12px; font-weight:900; letter-spacing:1px; }}
    QLabel#liveBadge {{ color:{ACCENT}; background:#103328; border:1px solid #236b51; border-radius:8px; padding:3px 8px; font-size:10px; font-weight:900; }}
    QLabel#logTime {{ color:#6f879f; font-family:Consolas; }}
    QLabel#logSource {{ color:#a8bad0; font-size:10px; font-weight:800; }}
    QPushButton#logClear {{ color:#9db0c5; background:#17283b; padding:4px 12px; }}
    QLabel#eventRow {{ background:#0d1928; border:1px solid #1e344c; border-radius:6px; padding:3px 9px; }}
    QLabel#brand {{ font-size: 20px; font-weight: 800; color: white; }}
    QLabel#eyebrow {{ color: {ACCENT}; font-weight: 700; font-size: 11px; }}
    QLabel#pageTitle {{ font-size: 23px; font-weight: 800; }}
    QLabel#muted {{ color: {MUTED}; }}
    QPushButton {{ border: none; border-radius: 10px; padding: 9px 14px; font-weight: 600; }}
    QPushButton:hover {{ background: #20334b; }}
    QPushButton#nav {{ color: {MUTED}; text-align: left; padding: 11px 14px; background: transparent; }}
    QPushButton#nav:hover {{ color: white; background: #15263b; }}
    QPushButton#nav:checked {{ color: white; background: #1a3f3b; border-left: 3px solid {ACCENT}; }}
    QPushButton#primary {{ color: #062016; background: {ACCENT}; }}
    QPushButton#primary:hover {{ background: #5ee3a4; }}
    QPushButton#danger {{ color: white; background: {DANGER}; }}
    QPushButton#icon {{ background: {SURFACE_2}; min-width: 22px; }}
    QFrame#card {{ background: rgba(16, 28, 45, 224); border: 1px solid rgba(77, 111, 143, 110); border-radius: 16px; }}
    QFrame#card:hover {{ border: 1px solid #4b7498; background: rgba(18, 33, 55, 238); }}
    QTableWidget {{ background: rgba(16, 28, 45, 232); alternate-background-color: rgba(18, 33, 55, 235); border: 1px solid #1f3148;
        border-radius: 14px; gridline-color: #1e3047; selection-background-color: #1d5949; }}
    QHeaderView::section {{ background: #17283e; color: {MUTED}; border: none; padding: 11px; font-weight: 700; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #31465f; border-radius: 4px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QComboBox, QSpinBox, QDoubleSpinBox {{ background: {SURFACE_2}; border: 1px solid #2a405b; border-radius: 9px; padding: 8px; }}
    QCheckBox {{ spacing: 10px; color: {MUTED}; }}
    QCheckBox::indicator {{ width: 38px; height: 20px; border-radius: 10px; background: #34465b; }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; }}
    QToolTip {{ background: #21344b; color: white; border: 1px solid #38526f; padding: 6px; }}
    """
