"""Modern operational overview dashboard for Luma with outsourced order notification and tracking."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.catalog import ProductCatalog
from core.config import get_config
from core.i18n import tr
from core.paths import get_data_path
from core.reporting import ReportingEngine
from core.seller_manager import SellerManager
from ui_components import EmptyStateWidget, MetricCard, SearchInput, SectionHeader, StatusBadge


class OutsourcedOrdersDialog(QDialog):
    """Detailed modal to inspect, review, and open outsourced orders."""

    def __init__(self, engine: ReportingEngine, language: str = "en", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine
        self.language = language
        self.resize(950, 580)
        self.setStyleSheet("background-color: #111827; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        top_row = QHBoxLayout()
        title_box = QVBoxLayout()
        self.title = QLabel("Outsourced Orders Overview")
        self.title.setObjectName("sectionTitle")
        self.subtitle = QLabel(
            "Orders containing outsourced barcodes sent to external fulfillment partners instead of being printed locally."
        )
        self.subtitle.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
        title_box.addWidget(self.title)
        title_box.addWidget(self.subtitle)
        top_row.addLayout(title_box, 1)

        self.btn_open_folder = QPushButton("Open Outsourced Folder")
        self.btn_open_folder.setObjectName("ghostButton")
        self.btn_open_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_folder.clicked.connect(self._open_folder)
        top_row.addWidget(self.btn_open_folder)
        layout.addLayout(top_row)

        # Filter bar
        filter_row = QHBoxLayout()
        self.search = SearchInput(placeholder="Filter by order number, customer, barcode...", debounce_ms=100)
        self.search.debounced_text_changed.connect(self._apply_filter)
        filter_row.addWidget(self.search, 2)

        self.btn_toggle_today = QPushButton("Show All Time")
        self.btn_toggle_today.setObjectName("ghostButton")
        self.btn_toggle_today.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_today.clicked.connect(self._toggle_scope)
        filter_row.addWidget(self.btn_toggle_today)

        layout.addLayout(filter_row)

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Order No.", "Customer", "Date / Time", "Seller", "Carrier", "Type", "Saved PDF"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.itemDoubleClicked.connect(self._open_selected_pdf)
        layout.addWidget(self.table, 1)

        # Actions Bottom
        actions_row = QHBoxLayout()
        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        actions_row.addWidget(self.lbl_count, 1)

        self.btn_open_pdf = QPushButton("Open Selected PDF")
        self.btn_open_pdf.setObjectName("primaryButton")
        self.btn_open_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_open_pdf.clicked.connect(self._open_selected_pdf)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("ghostButton")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)

        actions_row.addWidget(self.btn_open_pdf)
        actions_row.addWidget(self.btn_close)
        layout.addLayout(actions_row)

        self._show_today_only = True
        self._all_orders: List[Dict[str, Any]] = []
        self.set_language(language)
        self.refresh()

    def set_language(self, language: str) -> None:
        self.language = language
        self.setWindowTitle(tr("Outsourced Orders", language))
        self.title.setText(tr("Outsourced Orders Overview", language))
        self.subtitle.setText(
            tr(
                "Orders containing outsourced barcodes sent to external fulfillment partners instead of being printed locally.",
                language,
            )
        )
        self.btn_open_folder.setText(tr("Open Outsourced Folder", language))
        self.search.setPlaceholderText(tr("Filter by order number, customer, barcode...", language))
        self.btn_open_pdf.setText(tr("Open Selected PDF", language))
        self.btn_close.setText(tr("Close", language))
        self.btn_toggle_today.setText(
            tr("Show All Time", language) if self._show_today_only else tr("Show Today Only", language)
        )
        self.table.setHorizontalHeaderLabels([
            tr("Order No.", language),
            tr("Customer", language),
            tr("Timestamp", language),
            tr("Seller", language),
            tr("Cargo", language),
            tr("Type", language),
            tr("Saved PDF", language),
        ])

    def _toggle_scope(self) -> None:
        self._show_today_only = not self._show_today_only
        self.btn_toggle_today.setText(
            tr("Show All Time", self.language) if self._show_today_only else tr("Show Today Only", self.language)
        )
        self.refresh()

    def refresh(self) -> None:
        self._all_orders = self.engine.get_outsourced_orders(today_only=self._show_today_only)
        self.table.setRowCount(0)
        for order in self._all_orders:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(order["order_number"])))
            self.table.setItem(row, 1, QTableWidgetItem(str(order["customer"])))
            self.table.setItem(row, 2, QTableWidgetItem(str(order["at"])))
            self.table.setItem(row, 3, QTableWidgetItem(str(order["seller"])))
            self.table.setItem(row, 4, QTableWidgetItem(tr(str(order["carrier"]), self.language)))
            self.table.setItem(row, 5, QTableWidgetItem(tr(str(order["kind"]), self.language)))

            pdf_val = str(order["pdf"] or "—")
            pdf_item = QTableWidgetItem(os.path.basename(pdf_val) if pdf_val != "—" else "—")
            pdf_item.setData(Qt.UserRole, pdf_val)
            self.table.setItem(row, 6, pdf_item)

        scope_text = tr("today", self.language) if self._show_today_only else tr("all time", self.language)
        self.lbl_count.setText(
            f"{len(self._all_orders)} " + tr("outsourced order(s) found", self.language) + f" ({scope_text})"
        )
        self._apply_filter(self.search.text())

    def _apply_filter(self, query: str) -> None:
        query_norm = query.strip().casefold()
        for row in range(self.table.rowCount()):
            if not query_norm:
                self.table.setRowHidden(row, False)
                continue
            row_text = " ".join(
                self.table.item(row, col).text()
                for col in range(self.table.columnCount())
                if self.table.item(row, col)
            ).casefold()
            self.table.setRowHidden(row, query_norm not in row_text)

    def _open_selected_pdf(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, tr("Outsourced Orders", self.language), tr("Select an order from the table first.", self.language))
            return
        item = self.table.item(rows[0].row(), 6)
        pdf_path = item.data(Qt.UserRole) if item else None
        if not pdf_path or pdf_path == "—" or not os.path.exists(pdf_path):
            QMessageBox.information(
                self,
                tr("PDF Not Found", self.language),
                tr("The PDF file for this order is not stored at:\n{path}", self.language).format(path=pdf_path or "None"),
            )
            return

        try:
            if sys.platform.startswith("win"):
                os.startfile(pdf_path)
            else:
                subprocess.Popen(["xdg-open", pdf_path])
        except Exception as exc:
            QMessageBox.warning(self, tr("Error Opening PDF", self.language), str(exc))

    def _open_folder(self) -> None:
        folder = str(get_data_path("outsourced_labels"))
        os.makedirs(folder, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            QMessageBox.warning(self, tr("Open Folder", self.language), str(exc))


class DashboardTab(QWidget):
    """Operational dashboard providing at-a-glance metrics, outsourced alerts, and recent orders."""

    navigate_requested = Signal(int)  # Page index to navigate to

    def __init__(self, seller_manager: Optional[SellerManager] = None):
        super().__init__()
        self.seller_manager = seller_manager
        self.language = "en"
        self._reporting = ReportingEngine(
            state_file=str(get_data_path("printed_packages.json")),
            unknown_file=str(get_data_path("unknown_products.json")),
        )
        self._catalog = ProductCatalog(str(get_data_path("products.json")))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # Header with refresh button
        self.refresh_btn = QPushButton("Refresh Overview")
        self.refresh_btn.setObjectName("ghostButton")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_metrics)

        self.header = SectionHeader(
            title="Operational Overview",
            subtitle="Real-time fulfillment metrics, outsourced order tracking, and live order activity.",
            action_widget=self.refresh_btn,
        )
        layout.addWidget(self.header)

        # Top Metric Cards (5 cards in responsive grid)
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_active_sellers = MetricCard("Active Sellers", "0", "Connected stores", accent_color="#38bdf8")
        self.card_total_handled = MetricCard("Total Handled", "0", "All-time packages", accent_color="#2dd4bf")
        self.card_orders_today = MetricCard("Orders Processed Today", "0", "Thermal printed", accent_color="#34d399")
        self.card_outsourced_today = MetricCard("Outsourced Today", "0", "Forwarded to supplier", accent_color="#f59e0b")
        self.card_outsourced_today.setCursor(Qt.PointingHandCursor)
        self.card_outsourced_today.setToolTip("Click to view today's outsourced orders")
        self.card_outsourced_today.clicked.connect(self.open_outsourced_dialog)
        self.card_errors = MetricCard("Failed / Retrying", "0", "Requires attention", accent_color="#f87171")

        cards_layout.addWidget(self.card_active_sellers)
        cards_layout.addWidget(self.card_total_handled)
        cards_layout.addWidget(self.card_orders_today)
        cards_layout.addWidget(self.card_outsourced_today)
        cards_layout.addWidget(self.card_errors)
        layout.addLayout(cards_layout)

        # ---------------- Outsourced Orders Alert Banner ----------------
        self.outsourced_banner = QFrame()
        self.outsourced_banner.setObjectName("panel")
        self.outsourced_banner.setStyleSheet(
            "QFrame#panel { background-color: #1a2217; border: 1px solid #365314; border-radius: 10px; }"
        )
        banner_layout = QHBoxLayout(self.outsourced_banner)
        banner_layout.setContentsMargins(16, 12, 16, 12)
        banner_layout.setSpacing(12)

        self.lbl_outsourced_alert_icon = QLabel("📦")
        self.lbl_outsourced_alert_icon.setStyleSheet("font-size: 16pt;")
        banner_layout.addWidget(self.lbl_outsourced_alert_icon)

        banner_text_layout = QVBoxLayout()
        banner_text_layout.setSpacing(2)
        self.lbl_outsourced_alert_title = QLabel("Outsourced Orders Notice")
        self.lbl_outsourced_alert_title.setStyleSheet("color: #a3e635; font-weight: 700; font-size: 10.5pt;")
        self.lbl_outsourced_alert_msg = QLabel("0 outsourced orders processed today.")
        self.lbl_outsourced_alert_msg.setStyleSheet("color: #cbd5e1; font-size: 9pt;")
        banner_text_layout.addWidget(self.lbl_outsourced_alert_title)
        banner_text_layout.addWidget(self.lbl_outsourced_alert_msg)
        banner_layout.addLayout(banner_text_layout, 1)

        self.btn_view_outsourced = QPushButton("View Outsourced Orders (0)")
        self.btn_view_outsourced.setObjectName("primaryButton")
        self.btn_view_outsourced.setStyleSheet(
            "background-color: #4d7c0f; border-color: #65a30d; color: #ffffff;"
        )
        self.btn_view_outsourced.setCursor(Qt.PointingHandCursor)
        self.btn_view_outsourced.clicked.connect(self.open_outsourced_dialog)
        banner_layout.addWidget(self.btn_view_outsourced)

        layout.addWidget(self.outsourced_banner)

        # Operational Status Strip
        status_strip = QFrame()
        status_strip.setObjectName("panel")
        status_strip_layout = QHBoxLayout(status_strip)
        status_strip_layout.setContentsMargins(14, 10, 14, 10)

        self.lbl_automation_label = QLabel("Order Watcher:")
        self.lbl_automation_label.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 9pt;")
        self.badge_automation = StatusBadge("ACTIVE", "success")

        self.lbl_catalog_size_label = QLabel("Product Catalog:")
        self.lbl_catalog_size_label.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 9pt;")
        self.badge_catalog_size = StatusBadge("0 Products", "neutral")

        self.lbl_unknown_label = QLabel("Uncatalogued Barcodes:")
        self.lbl_unknown_label.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 9pt;")
        self.badge_unknown = StatusBadge("0 Discovered", "info")

        status_strip_layout.addWidget(self.lbl_automation_label)
        status_strip_layout.addWidget(self.badge_automation)
        status_strip_layout.addSpacing(20)
        status_strip_layout.addWidget(self.lbl_catalog_size_label)
        status_strip_layout.addWidget(self.badge_catalog_size)
        status_strip_layout.addSpacing(20)
        status_strip_layout.addWidget(self.lbl_unknown_label)
        status_strip_layout.addWidget(self.badge_unknown)
        status_strip_layout.addStretch()

        layout.addWidget(status_strip)

        # Recent Orders Table Section
        orders_header_layout = QHBoxLayout()
        self.recent_orders_label = QLabel("Recent Orders Across All Sellers")
        self.recent_orders_label.setObjectName("sectionTitle")
        orders_header_layout.addWidget(self.recent_orders_label)
        orders_header_layout.addStretch()

        self.btn_view_all_orders = QPushButton("Go to Orders & Labels →")
        self.btn_view_all_orders.setObjectName("ghostButton")
        self.btn_view_all_orders.setCursor(Qt.PointingHandCursor)
        self.btn_view_all_orders.clicked.connect(lambda: self.navigate_requested.emit(1))
        orders_header_layout.addWidget(self.btn_view_all_orders)

        layout.addLayout(orders_header_layout)

        self.order_table = QTableWidget(0, 7)
        self.order_table.setHorizontalHeaderLabels([
            "Timestamp", "Seller", "Order No.", "Package ID", "Customer", "Cargo", "Status"
        ])
        self.order_table.setAlternatingRowColors(True)
        self.order_table.verticalHeader().setVisible(False)
        self.order_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.order_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.order_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        layout.addWidget(self.order_table, 1)

        self._today_outsourced_count = 0
        self.set_language("en")
        self.populate_initial_orders()
        self.refresh_metrics()

    def set_seller_manager(self, manager: SellerManager) -> None:
        self.seller_manager = manager
        self.refresh_metrics()

    def set_automation_active(self, active: bool) -> None:
        if active:
            self.badge_automation.setText(tr("ACTIVE", self.language))
            self.badge_automation.set_variant("success")
        else:
            self.badge_automation.setText(tr("PAUSED", self.language))
            self.badge_automation.set_variant("warning")

    def set_language(self, language: str) -> None:
        self.language = language
        self.header.set_language(language)
        self.refresh_btn.setText(tr("Refresh Overview", language))
        self.card_active_sellers.set_language(language)
        self.card_total_handled.set_language(language)
        self.card_orders_today.set_language(language)
        self.card_outsourced_today.set_language(language)
        self.card_errors.set_language(language)

        self.lbl_outsourced_alert_title.setText(tr("Outsourced Orders Notice", language))
        self.btn_view_outsourced.setText(
            f"{tr('View Outsourced Orders', language)} ({self._today_outsourced_count})"
        )

        self.lbl_automation_label.setText(tr("Order Watcher:", language))
        self.lbl_catalog_size_label.setText(tr("Product Catalog:", language))
        self.lbl_unknown_label.setText(tr("Uncatalogued Barcodes:", language))
        self.recent_orders_label.setText(tr("Recent Orders Across All Sellers", language))
        self.btn_view_all_orders.setText(tr("Go to Orders & Labels →", language))

        self.order_table.setHorizontalHeaderLabels([
            tr("Timestamp", language),
            tr("Seller", language),
            tr("Order No.", language),
            tr("Package ID", language),
            tr("Customer", language),
            tr("Cargo", language),
            tr("Status", language),
        ])

        for row in range(self.order_table.rowCount()):
            for col in (5, 6):
                item = self.order_table.item(row, col)
                if item is not None:
                    raw_val = item.data(Qt.UserRole) or item.text()
                    item.setText(tr(str(raw_val), language))

    def refresh_metrics(self) -> None:
        """Derive real metrics from state and catalog without blocking GUI."""
        stats = self._reporting.get_summary()

        # 1. Total Handled
        self.card_total_handled.set_value(stats.total_packages)

        # 2. Orders today
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_data = stats.by_day.get(today_str, {})
        today_count = today_data.get("printed", 0)
        self.card_orders_today.set_value(today_count)

        # 3. Outsourced today
        outsourced_today = self._reporting.get_outsourced_orders(today_only=True)
        self._today_outsourced_count = len(outsourced_today)
        self.card_outsourced_today.set_value(self._today_outsourced_count)

        # Update banner
        if self._today_outsourced_count > 0:
            self.outsourced_banner.show()
            self.lbl_outsourced_alert_msg.setText(
                tr(
                    "{count} outsourced order(s) arrived today that were forwarded/saved as PDF instead of printed.",
                    self.language,
                ).format(count=self._today_outsourced_count)
            )
            self.btn_view_outsourced.setText(
                f"{tr('View Outsourced Orders', self.language)} ({self._today_outsourced_count})"
            )
        else:
            self.lbl_outsourced_alert_msg.setText(
                tr("No outsourced orders received today. Partner fulfillment is idle.", self.language)
            )
            self.btn_view_outsourced.setText(
                f"{tr('View Outsourced Orders', self.language)} (0)"
            )

        # 4. Active sellers
        if self.seller_manager:
            active_sellers = sum(
                p.is_active and p.monitoring_enabled for p in self.seller_manager.list_all()
            )
            self.card_active_sellers.set_value(active_sellers)

        # 5. Failed / errors
        self.card_errors.set_value(stats.failed_count)

        # 6. Catalog size
        catalog_count = len(self._catalog.list_all())
        self.badge_catalog_size.setText(f"{catalog_count} " + tr("Products", self.language))

        # 7. Unknown barcodes
        self.badge_unknown.setText(f"{stats.unknown_products_count} " + tr("Discovered", self.language))
        if stats.unknown_products_count > 0:
            self.badge_unknown.set_variant("warning")
        else:
            self.badge_unknown.set_variant("neutral")

    def open_outsourced_dialog(self) -> None:
        dialog = OutsourcedOrdersDialog(self._reporting, language=self.language, parent=self)
        dialog.exec()
        self.refresh_metrics()

    def populate_initial_orders(self) -> None:
        """Pre-populate the recent orders table with the latest handled packages from disk."""
        state = self._reporting._load_state()
        packages = state.get("packages", {})
        if not packages:
            return

        # Build seller_id -> display_tag map from SellerManager if available
        seller_names: Dict[str, str] = {}
        if self.seller_manager:
            for profile in self.seller_manager.list_all():
                seller_names[str(profile.seller_id)] = profile.display_tag

        sorted_items = sorted(
            packages.items(),
            key=lambda x: str(x[1].get("at") or ""),
            reverse=True,
        )[:40]

        self.order_table.setRowCount(0)
        for pid, meta in sorted_items:
            ts = str(meta.get("at") or "")
            # Prefer display_tag over raw seller ID stored in state
            seller_id_raw = str(meta.get("seller") or "")
            seller = seller_names.get(seller_id_raw) or (f"Seller {seller_id_raw}" if seller_id_raw else "—")
            order_no = str(meta.get("orderNumber") or meta.get("order_no") or pid)
            customer = str(meta.get("customer") or "—")
            cargo = str(meta.get("carrier") or "—")
            action = str(meta.get("action") or "processed")

            row = self.order_table.rowCount()
            self.order_table.insertRow(row)
            self.order_table.setItem(row, 0, QTableWidgetItem(ts))
            self.order_table.setItem(row, 1, QTableWidgetItem(seller))
            self.order_table.setItem(row, 2, QTableWidgetItem(order_no))
            self.order_table.setItem(row, 3, QTableWidgetItem(str(pid)))
            self.order_table.setItem(row, 4, QTableWidgetItem(customer))

            cargo_item = QTableWidgetItem(tr(cargo, self.language))
            cargo_item.setData(Qt.UserRole, cargo)
            self.order_table.setItem(row, 5, cargo_item)

            status_item = QTableWidgetItem(tr(action, self.language))
            status_item.setData(Qt.UserRole, action)
            self.order_table.setItem(row, 6, status_item)

    def add_order_row(self, timestamp: str, seller: str, order_no: str, cargo: str, status: str, customer: str = "—") -> None:
        """Slot invoked whenever worker threads process a package."""
        # Resolve seller display name if seller_manager is available
        seller_display = seller
        if self.seller_manager and seller:
            for profile in self.seller_manager.list_all():
                if str(profile.seller_id) == str(seller) or profile.display_tag == seller:
                    seller_display = profile.display_tag
                    break

        row_pos = 0
        self.order_table.insertRow(row_pos)
        self.order_table.setItem(row_pos, 0, QTableWidgetItem(str(timestamp)))
        self.order_table.setItem(row_pos, 1, QTableWidgetItem(str(seller_display)))
        self.order_table.setItem(row_pos, 2, QTableWidgetItem(str(order_no)))
        self.order_table.setItem(row_pos, 3, QTableWidgetItem(str(order_no)))
        self.order_table.setItem(row_pos, 4, QTableWidgetItem(str(customer)))

        cargo_item = QTableWidgetItem(tr(str(cargo), self.language))
        cargo_item.setData(Qt.UserRole, str(cargo))
        self.order_table.setItem(row_pos, 5, cargo_item)

        status_item = QTableWidgetItem(tr(str(status), self.language))
        status_item.setData(Qt.UserRole, str(status))
        self.order_table.setItem(row_pos, 6, status_item)

        if self.order_table.rowCount() > 100:
            self.order_table.removeRow(self.order_table.rowCount() - 1)

        self.refresh_metrics()
