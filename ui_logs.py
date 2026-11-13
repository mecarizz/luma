"""Modernized system activity logs viewer with search, filtering, and export."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.paths import get_data_path
from ui_components import SearchInput, SectionHeader, StatusBadge


class LogsTab(QWidget):
    """Activity logs console with search, level filtering, and diagnostics."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.language = "en"
        self._all_records: list[str] = []
        self._log_file_path = str(get_data_path("watcher.log"))

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(14)

        # Header
        self.header = SectionHeader(
            title="System Activity & Operational Logs",
            subtitle="Live watcher diagnostics, background polling events, and thermal printing outputs.",
        )
        root_layout.addWidget(self.header)

        # Controls & Filter Toolbar
        toolbar_card = QFrame()
        toolbar_card.setObjectName("panel")
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(14, 12, 14, 12)
        toolbar.setSpacing(10)

        self.search_input = SearchInput(placeholder="Filter logs by keyword...", debounce_ms=100)
        self.search_input.debounced_text_changed.connect(self._reapply_filter)
        toolbar.addWidget(self.search_input, 2)

        self.level_combo = QComboBox()
        self.level_combo.addItem("All Severities", "ALL")
        self.level_combo.addItem("Errors Only", "ERROR")
        self.level_combo.addItem("Warnings & Errors", "WARNING")
        self.level_combo.addItem("Info & Higher", "INFO")
        self.level_combo.currentIndexChanged.connect(self._reapply_filter)
        toolbar.addWidget(self.level_combo, 1)

        self.check_autoscroll = QCheckBox("Auto-scroll")
        self.check_autoscroll.setChecked(True)
        toolbar.addWidget(self.check_autoscroll)

        self.btn_copy_selected = QPushButton("Copy Selected")
        self.btn_copy_selected.setObjectName("ghostButton")
        self.btn_copy_selected.clicked.connect(self._copy_selected)

        self.btn_copy_all = QPushButton("Copy All")
        self.btn_copy_all.setObjectName("ghostButton")
        self.btn_copy_all.clicked.connect(self._copy_all)

        self.btn_clear = QPushButton("Clear Display")
        self.btn_clear.setObjectName("ghostButton")
        self.btn_clear.clicked.connect(self._clear_view)

        self.btn_open_file = QPushButton("Open Log File")
        self.btn_open_file.setObjectName("ghostButton")
        self.btn_open_file.clicked.connect(self._open_log_file)

        for btn in (self.btn_copy_selected, self.btn_copy_all, self.btn_clear, self.btn_open_file):
            btn.setCursor(Qt.PointingHandCursor)
            toolbar.addWidget(btn)

        root_layout.addWidget(toolbar_card)

        # Console viewer
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setStyleSheet(
            "QTextEdit { background-color: #0c121d; color: #cbd5e1; font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: 9.5pt; border: 1px solid #1e2b3e; border-radius: 10px; padding: 10px; line-height: 1.4; }"
        )
        root_layout.addWidget(self.log_viewer, 1)

        # Status Bar Footer
        status_row = QHBoxLayout()
        self.lbl_stats = QLabel("0 log lines recorded")
        self.lbl_stats.setStyleSheet("color: #64748b; font-size: 8.5pt;")

        self.badge_status = StatusBadge("LIVE LOGGING", "success")

        status_row.addWidget(self.lbl_stats, 1)
        status_row.addWidget(self.badge_status)
        root_layout.addLayout(status_row)

        self.set_language("en")
        self._load_existing_log_file()

    def set_language(self, language: str) -> None:
        self.language = language
        self.header.set_language(language)
        self.search_input.setPlaceholderText(tr("Filter logs by keyword...", language))
        self.check_autoscroll.setText(tr("Auto-scroll", language))
        self.btn_copy_selected.setText(tr("Copy Selected", language))
        self.btn_copy_all.setText(tr("Copy All", language))
        self.btn_clear.setText(tr("Clear Display", language))
        self.btn_open_file.setText(tr("Open Log File", language))

        curr_lvl = self.level_combo.currentData()
        self.level_combo.blockSignals(True)
        self.level_combo.clear()
        self.level_combo.addItem(tr("All Severities", language), "ALL")
        self.level_combo.addItem(tr("Errors Only", language), "ERROR")
        self.level_combo.addItem(tr("Warnings & Errors", language), "WARNING")
        self.level_combo.addItem(tr("Info & Higher", language), "INFO")
        idx = self.level_combo.findData(curr_lvl)
        self.level_combo.setCurrentIndex(max(0, idx))
        self.level_combo.blockSignals(False)

    def append_log(self, html_message: str) -> None:
        """Append a plain-text or HTML message emitted by worker threads."""
        text = str(html_message).strip()
        if not text:
            return
        self._all_records.append(text)
        # Cap in-memory lines to 5,000 for high performance
        if len(self._all_records) > 5000:
            self._all_records.pop(0)

        if self._matches_filter(text):
            self._render_log_line(text)

        self.lbl_stats.setText(f"{len(self._all_records)} " + tr("log lines recorded", self.language))

    def _render_log_line(self, line: str) -> None:
        cursor = self.log_viewer.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        lower = line.lower()
        if "error" in lower or "critical" in lower or "failed" in lower or "traceback" in lower:
            fmt.setForeground(QColor("#f87171"))  # Red
        elif "warning" in lower or "skipped" in lower:
            fmt.setForeground(QColor("#fbbf24"))  # Amber
        elif "started" in lower or "completed" in lower or "printed" in lower or "success" in lower:
            fmt.setForeground(QColor("#34d399"))  # Green
        elif re.match(r"^\[\d{4}-\d{2}-\d{2}", line):
            fmt.setForeground(QColor("#93c5fd"))  # Soft Blue
        else:
            fmt.setForeground(QColor("#cbd5e1"))  # Slate default

        cursor.insertText(line + "\n", fmt)
        if self.check_autoscroll.isChecked():
            self.log_viewer.setTextCursor(cursor)
            self.log_viewer.ensureCursorVisible()

    def _matches_filter(self, line: str) -> bool:
        query = self.search_input.text().strip().casefold()
        if query and query not in line.casefold():
            return False

        lvl = self.level_combo.currentData()
        lower = line.casefold()
        if lvl == "ERROR":
            return "error" in lower or "critical" in lower or "traceback" in lower
        elif lvl == "WARNING":
            return "warn" in lower or "error" in lower or "critical" in lower or "traceback" in lower
        return True

    def _reapply_filter(self) -> None:
        self.log_viewer.clear()
        for record in self._all_records:
            if self._matches_filter(record):
                self._render_log_line(record)

    def _copy_selected(self) -> None:
        cursor = self.log_viewer.textCursor()
        selected = cursor.selectedText()
        if selected:
            QApplication.clipboard().setText(selected)
        else:
            QMessageBox.information(
                self,
                tr("Copy Logs", self.language),
                tr("Please select text in the log viewer first.", self.language),
            )

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self.log_viewer.toPlainText())
        QMessageBox.information(
            self,
            tr("Copy Logs", self.language),
            tr("All visible log entries copied to clipboard.", self.language),
        )

    def _clear_view(self) -> None:
        self.log_viewer.clear()

    def _open_log_file(self) -> None:
        if os.path.exists(self._log_file_path):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(self._log_file_path)
                else:
                    subprocess.Popen(["xdg-open", self._log_file_path])
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    tr("Open Log File", self.language),
                    str(exc),
                )
        else:
            QMessageBox.information(
                self,
                tr("Open Log File", self.language),
                tr("Log file does not exist yet at:\n{path}", self.language).format(path=self._log_file_path),
            )

    def _load_existing_log_file(self) -> None:
        """Load trailing lines from disk log file if available."""
        if not os.path.exists(self._log_file_path):
            return
        try:
            with open(self._log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            for line in lines[-200:]:  # Load last 200 lines
                stripped = line.strip()
                if stripped:
                    self.append_log(stripped)
        except Exception:
            pass
