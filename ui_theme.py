"""Shared visual theme and design system tokens for the Luma desktop application."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# Color Palette Tokens
BG_BASE = "#0b0f19"         # Deep obsidian background
BG_SURFACE = "#111827"      # Sidebar & top header background
BG_PANEL = "#162032"        # Card / panel background
BG_ELEVATED = "#1e2c42"     # Hover / elevated element background
BG_INPUT = "#0f172a"        # Inputs, text fields, dropdowns

BORDER_SUBTLE = "#1e2b3e"   # Subtle separators
BORDER_DEFAULT = "#2a3b54"  # Default element border
BORDER_FOCUS = "#14b8a6"    # Active focus border (teal)

TEXT_PRIMARY = "#f8fafc"    # High emphasis text
TEXT_SECONDARY = "#94a3b8"  # Medium emphasis / muted text
TEXT_MUTED = "#64748b"      # Low emphasis text / disabled

ACCENT_TEAL = "#14b8a6"     # Primary brand accent
ACCENT_TEAL_HOVER = "#2dd4bf"
ACCENT_TEAL_ACTIVE = "#0d9488"
ACCENT_TEAL_SUBTLE = "#0e3538"

STATUS_SUCCESS_FG = "#34d399"
STATUS_SUCCESS_BG = "#064e3b"
STATUS_WARNING_FG = "#fbbf24"
STATUS_WARNING_BG = "#78350f"
STATUS_ERROR_FG = "#f87171"
STATUS_ERROR_BG = "#7f1d1d"
STATUS_INFO_FG = "#38bdf8"
STATUS_INFO_BG = "#0c4a6e"


def apply_dark_palette(application) -> None:
    """Keep native Qt controls readable regardless of the Windows color mode."""
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: QColor(BG_BASE),
        QPalette.ColorRole.WindowText: QColor(TEXT_PRIMARY),
        QPalette.ColorRole.Base: QColor(BG_INPUT),
        QPalette.ColorRole.AlternateBase: QColor(BG_PANEL),
        QPalette.ColorRole.ToolTipBase: QColor(BG_ELEVATED),
        QPalette.ColorRole.ToolTipText: QColor(TEXT_PRIMARY),
        QPalette.ColorRole.Text: QColor(TEXT_PRIMARY),
        QPalette.ColorRole.Button: QColor(BG_PANEL),
        QPalette.ColorRole.ButtonText: QColor(TEXT_PRIMARY),
        QPalette.ColorRole.BrightText: QColor("#ffffff"),
        QPalette.ColorRole.Highlight: QColor(ACCENT_TEAL_ACTIVE),
        QPalette.ColorRole.HighlightedText: QColor("#ffffff"),
        QPalette.ColorRole.PlaceholderText: QColor(TEXT_SECONDARY),
    }
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        for role, color in colors.items():
            palette.setColor(group, role, color)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.HighlightedText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(TEXT_MUTED))
    application.setPalette(palette)


DARK_STYLESHEET = """
/* Base Application & Window Styling */
QMainWindow, QWidget#appRoot {
    background-color: #0b0f19;
    color: #f8fafc;
}

QWidget {
    color: #f8fafc;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Inter", Roboto, sans-serif;
    font-size: 10pt;
    selection-background-color: #134e4a;
    selection-color: #ffffff;
}

/* Menu Bar & Menus */
QMenuBar {
    background-color: #111827;
    color: #cbd5e1;
    padding: 4px 8px;
    border-bottom: 1px solid #1e2b3e;
    font-size: 9.5pt;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 6px;
}

QMenuBar::item:selected {
    background-color: #1e2c42;
    color: #f8fafc;
}

QMenu {
    background-color: #111827;
    border: 1px solid #2a3b54;
    border-radius: 8px;
    padding: 6px;
    color: #f8fafc;
}

QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 6px;
}

QMenu::item:selected {
    background-color: #1e2c42;
    color: #2dd4bf;
}

QMenu::separator {
    height: 1px;
    background-color: #1e2b3e;
    margin: 4px 8px;
}

/* Status Bar */
QStatusBar {
    background-color: #0b0f19;
    color: #94a3b8;
    border-top: 1px solid #1e2b3e;
    padding: 4px 12px;
    font-size: 9pt;
}

/* Left Sidebar */
QFrame#sidebar {
    background-color: #111827;
    border-right: 1px solid #1e2b3e;
}

QLabel#brand {
    color: #f8fafc;
    font-size: 17pt;
    font-weight: 800;
    letter-spacing: 0.5px;
}

QLabel#brandMark {
    color: #2dd4bf;
    font-size: 22pt;
    font-weight: 800;
}

QLabel#tagline {
    color: #64748b;
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 1.5px;
}

QLabel#muted {
    color: #94a3b8;
}

QLabel#pageTitle {
    color: #f8fafc;
    font-size: 20pt;
    font-weight: 700;
    letter-spacing: -0.3px;
}

QLabel#pageSubtitle {
    color: #94a3b8;
    font-size: 9.5pt;
}

QLabel#sectionTitle {
    color: #f8fafc;
    font-size: 11.5pt;
    font-weight: 700;
}

QLabel#accent {
    color: #2dd4bf;
    font-weight: 700;
}

/* Sidebar Navigation Buttons */
QPushButton#navButton {
    text-align: left;
    padding: 10px 14px;
    border: 1px solid transparent;
    border-radius: 8px;
    color: #94a3b8;
    background-color: transparent;
    font-size: 10pt;
    font-weight: 600;
}

QPushButton#navButton:hover {
    background-color: #162234;
    color: #f8fafc;
}

QPushButton#navButton:checked {
    background-color: #0e3538;
    color: #2dd4bf;
    border: 1px solid #134e4a;
    font-weight: 700;
}

QPushButton#versionStatus {
    color: #94a3b8;
    background-color: transparent;
    border: 1px solid transparent;
    text-align: left;
    padding: 5px 2px;
    font-size: 8.5pt;
}

QPushButton#versionStatus:hover {
    color: #f8fafc;
    background-color: #162032;
}

QPushButton#versionStatusImportant {
    color: #fbbf24;
    background-color: #78350f;
    border: 1px solid #92400e;
    text-align: left;
    padding: 5px 8px;
    font-size: 8.5pt;
}

QPushButton#versionStatusCritical {
    color: #f87171;
    background-color: #7f1d1d;
    border: 1px solid #991b1b;
    text-align: left;
    padding: 5px 8px;
    font-size: 8.5pt;
    font-weight: 700;
}

QPushButton#navButton:focus {
    outline: none;
}

/* System Status Pill in Sidebar */
QFrame#systemPill {
    background-color: #162032;
    border: 1px solid #1e2b3e;
    border-radius: 10px;
    padding: 10px;
}

/* Cards & Panels */
QFrame#metricCard, QFrame#panel {
    background-color: #162032;
    border: 1px solid #1e2b3e;
    border-radius: 12px;
}

QFrame#metricCard:hover {
    border-color: #2a3b54;
}

QLabel#metricTitle {
    color: #94a3b8;
    font-size: 8.5pt;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QLabel#metricValue {
    color: #f8fafc;
    font-size: 22pt;
    font-weight: 750;
    letter-spacing: -0.5px;
}

QLabel#metricSubtitle {
    color: #64748b;
    font-size: 8pt;
}

/* Data Tables */
QTableWidget {
    background-color: #121a28;
    alternate-background-color: #162032;
    color: #e2e8f0;
    gridline-color: #1e2b3e;
    border: 1px solid #1e2b3e;
    border-radius: 10px;
    selection-background-color: #134e4a;
    selection-color: #ffffff;
    outline: none;
}

QHeaderView::section {
    background-color: #162032;
    color: #94a3b8;
    padding: 9px 10px;
    border: 0;
    border-bottom: 1px solid #2a3b54;
    font-size: 8.5pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QHeaderView::section:hover {
    background-color: #1e2c42;
    color: #f8fafc;
}

QTableWidget::item {
    padding: 8px 10px;
    border-bottom: 1px solid #182234;
}

QTableWidget::item:selected {
    background-color: #134e4a;
    color: #ffffff;
}

/* Inputs & Form Controls */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit, QPlainTextEdit, QListWidget {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #2a3b54;
    border-radius: 8px;
    padding: 8px 11px;
    font-size: 9.5pt;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #14b8a6;
    background-color: #111c2e;
}

QLineEdit:disabled, QComboBox:disabled {
    color: #64748b;
    background-color: #0b1120;
    border-color: #1e293b;
}

/* Dropdown / QComboBox specific */
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left-width: 0px;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #94a3b8;
    margin-right: 10px;
}

QComboBox QAbstractItemView {
    background-color: #111827;
    color: #f8fafc;
    border: 1px solid #2a3b54;
    border-radius: 8px;
    selection-background-color: #134e4a;
    selection-color: #ffffff;
    padding: 4px;
}

/* Buttons */
QPushButton {
    background-color: #1e2c42;
    color: #f8fafc;
    border: 1px solid #2a3b54;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 9.5pt;
}

QPushButton:hover {
    background-color: #273752;
    border-color: #3b4e6b;
}

QPushButton:pressed {
    background-color: #162032;
}

QPushButton:disabled {
    color: #64748b;
    background-color: #111827;
    border-color: #1e293b;
}

/* Primary Action Button (Teal Accent) */
QPushButton#primaryButton {
    background-color: #0d9488;
    color: #ffffff;
    border: 1px solid #14b8a6;
    font-weight: 700;
}

QPushButton#primaryButton:hover {
    background-color: #14b8a6;
    border-color: #2dd4bf;
}

QPushButton#primaryButton:pressed {
    background-color: #0f766e;
}

QPushButton#primaryButton:disabled {
    background-color: #134e4a;
    color: #5eead4;
    opacity: 0.5;
    border-color: transparent;
}

/* Destructive Button (Red Accent) */
QPushButton#destructiveButton {
    background-color: #451a1a;
    color: #fca5a5;
    border: 1px solid #7f1d1d;
    font-weight: 600;
}

QPushButton#destructiveButton:hover {
    background-color: #7f1d1d;
    color: #fee2e2;
    border-color: #ef4444;
}

QPushButton#destructiveButton:pressed {
    background-color: #991b1b;
}

/* Secondary / Ghost Buttons */
QPushButton#ghostButton {
    background-color: transparent;
    border: 1px solid #2a3b54;
    color: #cbd5e1;
}

QPushButton#ghostButton:hover {
    background-color: #162032;
    color: #f8fafc;
}

/* Checkboxes */
QCheckBox {
    spacing: 8px;
    color: #e2e8f0;
    font-size: 9.5pt;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #334155;
    background-color: #0f172a;
}

QCheckBox::indicator:hover {
    border-color: #14b8a6;
}

QCheckBox::indicator:checked {
    background-color: #0d9488;
    border-color: #14b8a6;
    image: none;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: #0b0f19;
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #2a3b54;
    border-radius: 5px;
    min-height: 28px;
}

QScrollBar::handle:vertical:hover {
    background-color: #3b4e6b;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    height: 0px;
    background: transparent;
}

QScrollBar:horizontal {
    background-color: #0b0f19;
    height: 10px;
    margin: 2px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background-color: #2a3b54;
    border-radius: 5px;
    min-width: 28px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: transparent;
}

/* Splitter */
QSplitter::handle {
    background-color: #1e2b3e;
}

/* TabWidget inside pages */
QTabWidget::pane {
    border: 1px solid #1e2b3e;
    border-radius: 10px;
    background-color: #111827;
    top: -1px;
}

QTabBar::tab {
    background-color: #162032;
    color: #94a3b8;
    padding: 8px 18px;
    border: 1px solid #1e2b3e;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #111827;
    color: #2dd4bf;
    border-top: 2px solid #14b8a6;
}

QTabBar::tab:hover:!selected {
    background-color: #1e2c42;
    color: #f8fafc;
}

/* Dialog Styling */
QDialog {
    background-color: #111827;
    color: #f8fafc;
}

/* Tooltip */
QToolTip {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 9pt;
}

/* Empty State & Help Containers */
QFrame#emptyState {
    background-color: #121a28;
    border: 1px dashed #2a3b54;
    border-radius: 12px;
    padding: 36px 24px;
}

QLabel#emptyStateTitle {
    color: #f8fafc;
    font-size: 13pt;
    font-weight: 700;
}

QLabel#emptyStateText {
    color: #94a3b8;
    font-size: 9.5pt;
}
"""
