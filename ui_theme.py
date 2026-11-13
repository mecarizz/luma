"""Shared visual theme for the Luma desktop application."""

DARK_STYLESHEET = """
QMainWindow, QWidget#appRoot { background: #101720; color: #e7edf3; }
QWidget { color: #e7edf3; font-family: "Segoe UI"; font-size: 10pt; }
QMenuBar { background: #151f2b; color: #dbe5ee; padding: 5px 10px; border-bottom: 1px solid #263445; }
QMenuBar::item { padding: 7px 12px; border-radius: 6px; }
QMenuBar::item:selected, QMenu::item:selected { background: #263847; }
QMenu { background: #192431; border: 1px solid #344456; padding: 6px; }
QMenu::item { padding: 7px 24px; }
QStatusBar { background: #121c27; color: #91a3b7; border-top: 1px solid #263445; }
QFrame#sidebar { background: #151f2b; border-right: 1px solid #263445; }
QLabel#brand { color: #f4f8fb; font-size: 22pt; font-weight: 800; letter-spacing: 1px; }
QLabel#brandMark { color: #2dd4bf; font-size: 28pt; font-weight: 800; }
QLabel#muted { color: #91a3b7; }
QLabel#pageTitle { color: #f4f8fb; font-size: 23pt; font-weight: 700; }
QLabel#subtitle { color: #9fb0c2; font-size: 10pt; }
QPushButton#navButton { text-align: left; padding: 11px 14px; border: 0; border-radius: 9px; color: #b9c7d6; background: transparent; font-weight: 600; }
QPushButton#navButton:hover { background: #202e3d; color: #f4f8fb; }
QPushButton#navButton:checked { background: #164c4b; color: #eafffb; border-left: 3px solid #2dd4bf; }
QFrame#metricCard, QFrame#panel { background: #182432; border: 1px solid #2a3a4d; border-radius: 12px; }
QLabel#metricTitle { color: #9fb0c2; font-size: 9pt; font-weight: 600; }
QLabel#metricValue { color: #f4f8fb; font-size: 25pt; font-weight: 750; }
QLabel#accent { color: #2dd4bf; font-weight: 700; }
QLabel#sectionTitle { color: #f1f6fa; font-size: 12pt; font-weight: 700; }
QTableWidget { background: #172331; alternate-background-color: #1b2938; color: #e0e8f0; gridline-color: #2a3949; border: 1px solid #2a3a4d; border-radius: 8px; selection-background-color: #205b5a; selection-color: white; }
QHeaderView::section { background: #202e3d; color: #aebed0; padding: 10px 8px; border: 0; border-bottom: 1px solid #344456; font-weight: 700; }
QTableWidget::item { padding: 7px; }
QLineEdit, QComboBox, QSpinBox, QDateEdit, QTextEdit, QPlainTextEdit, QListWidget { background: #111c28; color: #e7edf3; border: 1px solid #344456; border-radius: 7px; padding: 8px; selection-background-color: #205b5a; }
QComboBox QAbstractItemView { background: #192431; color: #e7edf3; selection-background-color: #205b5a; }
QPushButton { background: #263849; color: #eaf2f8; border: 1px solid #3a5065; border-radius: 7px; padding: 8px 13px; font-weight: 600; }
QPushButton:hover { background: #30485d; }
QPushButton:pressed { background: #1e3548; }
QPushButton:disabled { color: #718196; background: #202b37; }
QCheckBox { spacing: 8px; color: #cbd7e3; }
QScrollBar:vertical { background: #121c27; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #405469; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
