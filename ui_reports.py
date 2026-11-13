"""Comprehensive fulfillment reports and operational analytics tab."""
from __future__ import annotations

import csv
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.paths import get_data_path
from core.reporting import ReportingEngine
from ui_components import MetricCard, SectionHeader, StatusBadge


class ReportsTab(QWidget):
    """Fulfillment reporting, carrier breakdown, and CSV audit export."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.language = "en"
        self._engine = ReportingEngine(
            state_file=str(get_data_path("printed_packages.json")),
            unknown_file=str(get_data_path("unknown_products.json")),
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(14)

        # Header with actions
        header_actions = QHBoxLayout()
        header_actions.setSpacing(8)

        self.btn_refresh = QPushButton("Refresh Report")
        self.btn_refresh.setObjectName("ghostButton")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_report)

        self.btn_export = QPushButton("Export Audit CSV")
        self.btn_export.setObjectName("primaryButton")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.export_csv)

        header_actions.addWidget(self.btn_refresh)
        header_actions.addWidget(self.btn_export)

        header_container = QWidget()
        header_container.setLayout(header_actions)

        self.header = SectionHeader(
            title="Fulfillment & Operational Reports",
            subtitle="Aggregated throughput, carrier utilization, seller breakdowns, and audit exports.",
            action_widget=header_container,
        )
        root_layout.addWidget(self.header)

        # Top Summary Metric Cards
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self.card_total = MetricCard("Total Handled", "0", "All historical packages", accent_color="#2dd4bf")
        self.card_printed = MetricCard("Labels Printed", "0", "Thermal printed", accent_color="#34d399")
        self.card_outsourced = MetricCard("Outsourced", "0", "Supplier forwarded", accent_color="#38bdf8")
        self.card_failed = MetricCard("Failed / Blocked", "0", "Carrier/print errors", accent_color="#f87171")

        metrics_layout.addWidget(self.card_total)
        metrics_layout.addWidget(self.card_printed)
        metrics_layout.addWidget(self.card_outsourced)
        metrics_layout.addWidget(self.card_failed)
        root_layout.addLayout(metrics_layout)

        # Sub-tabs for detailed reports
        self.tabs = QTabWidget()

        # Tab 1: Daily Throughput
        self.daily_table = QTableWidget(0, 6)
        self.daily_table.setHorizontalHeaderLabels(["Date", "Total Handled", "Printed", "Outsourced", "Mixed", "Failed"])
        self.daily_table.setAlternatingRowColors(True)
        self.daily_table.verticalHeader().setVisible(False)
        self.daily_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabs.addTab(self.daily_table, "Daily Fulfillment")

        # Tab 2: Carrier Breakdown
        self.carrier_table = QTableWidget(0, 3)
        self.carrier_table.setHorizontalHeaderLabels(["Carrier", "Packages Handled", "Share (%)"])
        self.carrier_table.setAlternatingRowColors(True)
        self.carrier_table.verticalHeader().setVisible(False)
        self.carrier_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabs.addTab(self.carrier_table, "Carrier Utilization")

        # Tab 3: Seller Distribution
        self.seller_table = QTableWidget(0, 5)
        self.seller_table.setHorizontalHeaderLabels(["Seller", "Total Handled", "Printed", "Outsourced", "Failed"])
        self.seller_table.setAlternatingRowColors(True)
        self.seller_table.verticalHeader().setVisible(False)
        self.seller_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabs.addTab(self.seller_table, "Seller Breakdown")

        root_layout.addWidget(self.tabs, 1)

        self.set_language("en")
        self.refresh_report()

    def set_language(self, language: str) -> None:
        self.language = language
        self.header.set_language(language)
        self.btn_refresh.setText(tr("Refresh Report", language))
        self.btn_export.setText(tr("Export Audit CSV", language))

        self.card_total.set_language(language)
        self.card_printed.set_language(language)
        self.card_outsourced.set_language(language)
        self.card_failed.set_language(language)

        self.tabs.setTabText(0, tr("Daily Fulfillment", language))
        self.tabs.setTabText(1, tr("Carrier Utilization", language))
        self.tabs.setTabText(2, tr("Seller Breakdown", language))

        self.daily_table.setHorizontalHeaderLabels([
            tr("Date", language),
            tr("Total Handled", language),
            tr("Printed", language),
            tr("Outsourced", language),
            tr("Mixed", language),
            tr("Failed", language),
        ])

        self.carrier_table.setHorizontalHeaderLabels([
            tr("Carrier", language),
            tr("Packages Handled", language),
            tr("Share (%)", language),
        ])

        self.seller_table.setHorizontalHeaderLabels([
            tr("Seller", language),
            tr("Total Handled", language),
            tr("Printed", language),
            tr("Outsourced", language),
            tr("Failed", language),
        ])
        self.refresh_report()

    def refresh_report(self) -> None:
        stats = self._engine.get_summary()

        self.card_total.set_value(stats.total_packages)
        self.card_printed.set_value(stats.printed_count)
        self.card_outsourced.set_value(stats.outsourced_count)
        self.card_failed.set_value(stats.failed_count)

        # 1. Populate Daily Table
        self.daily_table.setRowCount(0)
        for day, m in sorted(stats.by_day.items(), reverse=True):
            row = self.daily_table.rowCount()
            self.daily_table.insertRow(row)
            self.daily_table.setItem(row, 0, QTableWidgetItem(day))
            self.daily_table.setItem(row, 1, QTableWidgetItem(str(m.get("total", 0))))
            self.daily_table.setItem(row, 2, QTableWidgetItem(str(m.get("printed", 0))))
            self.daily_table.setItem(row, 3, QTableWidgetItem(str(m.get("outsourced", 0))))
            self.daily_table.setItem(row, 4, QTableWidgetItem(str(m.get("mixed", 0))))
            self.daily_table.setItem(row, 5, QTableWidgetItem(str(m.get("failed", 0))))

        # 2. Populate Carrier Table
        self.carrier_table.setRowCount(0)
        total_carrier_pkgs = sum(stats.by_carrier.values()) or 1
        for carrier, count in sorted(stats.by_carrier.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_carrier_pkgs) * 100
            row = self.carrier_table.rowCount()
            self.carrier_table.insertRow(row)
            self.carrier_table.setItem(row, 0, QTableWidgetItem(tr(carrier, self.language)))
            self.carrier_table.setItem(row, 1, QTableWidgetItem(str(count)))
            self.carrier_table.setItem(row, 2, QTableWidgetItem(f"{pct:.1f}%"))

        # 3. Populate Seller Table
        self.seller_table.setRowCount(0)
        for seller, sm in sorted(stats.by_seller.items(), key=lambda x: x[1].get("total", 0), reverse=True):
            row = self.seller_table.rowCount()
            self.seller_table.insertRow(row)
            self.seller_table.setItem(row, 0, QTableWidgetItem(str(seller)))
            self.seller_table.setItem(row, 1, QTableWidgetItem(str(sm.get("total", 0))))
            self.seller_table.setItem(row, 2, QTableWidgetItem(str(sm.get("printed", 0))))
            self.seller_table.setItem(row, 3, QTableWidgetItem(str(sm.get("outsourced", 0))))
            self.seller_table.setItem(row, 4, QTableWidgetItem(str(sm.get("failed", 0))))

    def export_csv(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export Audit Report to CSV", self.language),
            "luma_order_audit.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        try:
            self._engine.export_audit_csv(file_path)
            QMessageBox.information(
                self,
                tr("Export Successful", self.language),
                tr("Exported audit report to:\n{path}", self.language).format(path=file_path),
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                tr("Export Failed", self.language),
                str(exc),
            )
