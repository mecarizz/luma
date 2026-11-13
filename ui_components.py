"""Reusable UI components for the modern Luma desktop application."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr


class MetricCard(QFrame):
    """Modern SaaS metric card displaying a high-level operational figure."""

    clicked = Signal()

    def __init__(
        self,
        title: str,
        initial_value: str = "0",
        subtitle: str = "",
        accent_color: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setFrameShape(QFrame.StyledPanel)
        self._title = title
        self._subtitle = subtitle
        self.language = "en"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        # Header with title
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("metricTitle")
        layout.addWidget(self.lbl_title)

        # Big Value
        self.lbl_value = QLabel(initial_value)
        self.lbl_value.setObjectName("metricValue")
        if accent_color:
            self.lbl_value.setStyleSheet(f"color: {accent_color};")
        layout.addWidget(self.lbl_value)

        # Subtitle / trend
        self.lbl_subtitle = QLabel(subtitle)
        self.lbl_subtitle.setObjectName("metricSubtitle")
        if not subtitle:
            self.lbl_subtitle.hide()
        layout.addWidget(self.lbl_subtitle)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()

    def set_value(self, value: str | int) -> None:
        self.lbl_value.setText(str(value))

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle = subtitle
        self.lbl_subtitle.setText(tr(subtitle, self.language))
        self.lbl_subtitle.setVisible(bool(subtitle))

    def set_language(self, language: str) -> None:
        self.language = language
        self.lbl_title.setText(tr(self._title, language))
        if self._subtitle:
            self.lbl_subtitle.setText(tr(self._subtitle, language))


class StatusBadge(QLabel):
    """Colored status badge/pill indicating states like Active, Picking, Error, etc."""

    VARIANT_STYLES = {
        "success": "background-color: #064e3b; color: #34d399; border: 1px solid #059669;",
        "warning": "background-color: #78350f; color: #fbbf24; border: 1px solid #d97706;",
        "error": "background-color: #7f1d1d; color: #f87171; border: 1px solid #dc2626;",
        "info": "background-color: #0c4a6e; color: #38bdf8; border: 1px solid #0284c7;",
        "neutral": "background-color: #1e293b; color: #94a3b8; border: 1px solid #334155;",
    }

    def __init__(self, text: str = "", variant: str = "neutral", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        style = self.VARIANT_STYLES.get(variant, self.VARIANT_STYLES["neutral"])
        self.setStyleSheet(
            f"{style} border-radius: 6px; padding: 3px 8px; font-size: 8.5pt; font-weight: 700;"
        )


class SearchInput(QLineEdit):
    """Search input field with integrated debouncing to prevent lagging during fast typing."""

    debounced_text_changed = Signal(str)

    def __init__(
        self,
        placeholder: str = "Search...",
        debounce_ms: int = 250,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._emit_debounced)
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str) -> None:
        self._timer.start()

    def _emit_debounced(self) -> None:
        self.debounced_text_changed.emit(self.text())


class EmptyStateWidget(QFrame):
    """Card presented when a table, search result, or list has no items."""

    def __init__(
        self,
        title: str,
        description: str,
        icon: str = "◇",
        button_text: Optional[str] = None,
        button_callback: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("emptyState")
        self._title = title
        self._description = description
        self.language = "en"

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        lbl_icon = QLabel(icon)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet("color: #64748b; font-size: 28pt; margin-bottom: 4px;")
        layout.addWidget(lbl_icon)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("emptyStateTitle")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_title)

        self.lbl_desc = QLabel(description)
        self.lbl_desc.setObjectName("emptyStateText")
        self.lbl_desc.setAlignment(Qt.AlignCenter)
        self.lbl_desc.setWordWrap(True)
        layout.addWidget(self.lbl_desc)

        if button_text and button_callback:
            layout.addSpacing(6)
            self.action_btn = QPushButton(button_text)
            self.action_btn.setObjectName("primaryButton")
            self.action_btn.setCursor(Qt.PointingHandCursor)
            self.action_btn.clicked.connect(button_callback)
            layout.addWidget(self.action_btn, 0, Qt.AlignCenter)
        else:
            self.action_btn = None

    def set_language(self, language: str) -> None:
        self.language = language
        self.lbl_title.setText(tr(self._title, language))
        self.lbl_desc.setText(tr(self._description, language))


class SectionHeader(QWidget):
    """Consistent section header with title, subtitle, and action widgets."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        action_widget: Optional[QWidget] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self.language = "en"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("sectionTitle")
        text_layout.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel(subtitle)
        self.lbl_subtitle.setObjectName("pageSubtitle")
        if not subtitle:
            self.lbl_subtitle.hide()
        text_layout.addWidget(self.lbl_subtitle)

        layout.addLayout(text_layout, 1)

        if action_widget:
            layout.addWidget(action_widget, 0, Qt.AlignRight | Qt.AlignVCenter)

    def set_language(self, language: str) -> None:
        self.language = language
        self.lbl_title.setText(tr(self._title, language))
        if self._subtitle:
            self.lbl_subtitle.setText(tr(self._subtitle, language))
