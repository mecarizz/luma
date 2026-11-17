"""Simplified order line view for bookkeeping."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.seller_models import SellerProfile
from ui_components import SearchInput, SectionHeader
from ui_orders import _FetchOrdersWorker


def _format_price(value: object, quantity: int = 1) -> str:
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(str(value).replace(",", "."))
        amount = (amount * quantity).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return str(value)
    formatted = f"{amount:,.2f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _order_timestamp(package: Dict[str, Any]) -> float:
    for field in ("orderDate", "packageLastModifiedDate"):
        value = package.get(field)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return float("-inf")


def _bookkeeping_rows(
    packages: Iterable[Dict[str, Any]],
) -> List[Tuple[str, str, str, str]]:
    rows = []
    ordered_packages = sorted(
        packages,
        key=_order_timestamp,
        reverse=True,
    )
    for package in ordered_packages:
        address = package.get("shipmentAddress") or {}
        customer = str(address.get("fullName") or "—").strip() or "—"
        district = str(address.get("district") or "").strip()
        city = str(address.get("city") or "").strip()
        location = (
            f"{district}/{city}"
            if district and city and district.casefold() != city.casefold()
            else district or city or "—"
        )

        for line in package.get("lines") or []:
            product = str(line.get("productName") or line.get("barcode") or "—").strip()
            quantity_value = line.get("quantity") or 1
            try:
                quantity = max(1, int(quantity_value))
            except (TypeError, ValueError):
                quantity = 1
            if quantity > 1:
                product = f"{product} x {quantity}"
            price = line.get("amount")
            if price is None:
                price = line.get("discountedPrice")
                if price is None:
                    price = line.get("price")
                rows.append((customer, location, product, _format_price(price, quantity)))
            else:
                rows.append((customer, location, product, _format_price(price)))
    return rows


class BookkeepingTab(QWidget):
    operation_started = Signal()
    operation_finished = Signal()
    log_emitted = Signal(str)

    HEADERS = ("Customer", "Address", "Product", "Price")

    def __init__(self):
        super().__init__()
        self.language = "en"
        self.seller_manager = None
        self._profiles: List[SellerProfile] = []
        self._worker: Optional[_FetchOrdersWorker] = None
        self._status_template = "Choose a date range and fetch orders."
        self._status_values: Dict[str, Any] = {}
        self._loaded_order_count = 0
        self._loaded_line_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.header = SectionHeader(
            title="Bookkeeping",
            subtitle="Fetch order line items for a date range with only the details you need.",
        )
        layout.addWidget(self.header)

        controls = QFrame()
        controls.setObjectName("panel")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(10)

        self.seller_label = QLabel("Seller:")
        self.seller_combo = QComboBox()
        self.seller_combo.setMinimumWidth(180)

        self.start_date_label = QLabel("From:")
        self.start_date_input = QDateEdit()
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDisplayFormat("yyyy-MM-dd")

        self.end_date_label = QLabel("To:")
        self.end_date_input = QDateEdit()
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDisplayFormat("yyyy-MM-dd")
        today = self.end_date_input.date()
        self.end_date_input.setDate(today)
        self.start_date_input.setDate(today.addDays(-6))

        self.max_orders_label = QLabel("Maximum orders:")
        self.max_orders_input = QSpinBox()
        self.max_orders_input.setRange(1, 10000)
        self.max_orders_input.setValue(10000)
        self.max_orders_input.setSingleStep(200)

        self.fetch_button = QPushButton("Fetch Orders")
        self.fetch_button.setObjectName("primaryButton")
        self.fetch_button.clicked.connect(self.fetch_orders)

        controls_layout.addWidget(self.seller_label)
        controls_layout.addWidget(self.seller_combo)
        controls_layout.addWidget(self.start_date_label)
        controls_layout.addWidget(self.start_date_input)
        controls_layout.addWidget(self.end_date_label)
        controls_layout.addWidget(self.end_date_input)
        controls_layout.addWidget(self.max_orders_label)
        controls_layout.addWidget(self.max_orders_input)
        controls_layout.addWidget(self.fetch_button)
        layout.addWidget(controls)

        self.search_input = SearchInput(
            placeholder="Find customer, address, product, or price...",
            debounce_ms=150,
        )
        self.search_input.debounced_text_changed.connect(self._apply_filter)
        layout.addWidget(self.search_input)

        self.status_label = QLabel("Choose a date range and fetch orders.")
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
        layout.addWidget(self.status_label)

        self.order_table = QTableWidget(0, len(self.HEADERS))
        self.order_table.setHorizontalHeaderLabels(list(self.HEADERS))
        self.order_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.order_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.order_table.setAlternatingRowColors(True)
        self.order_table.verticalHeader().setVisible(False)
        self.order_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.order_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        layout.addWidget(self.order_table, 1)

        self.set_language("en")
        self._update_enabled()

    def set_language(self, language: str) -> None:
        self.language = language if language in ("en", "tr") else "en"
        self.header.set_language(self.language)
        self.seller_label.setText(tr("Seller:", self.language))
        self.start_date_label.setText(tr("From:", self.language))
        self.end_date_label.setText(tr("To:", self.language))
        self.max_orders_label.setText(tr("Maximum orders:", self.language))
        self.fetch_button.setText(tr("Fetch Orders", self.language))
        self.search_input.setPlaceholderText(
            tr("Find customer, address, product, or price...", self.language)
        )
        self.order_table.setHorizontalHeaderLabels(
            [tr(header, self.language) for header in self.HEADERS]
        )
        self.status_label.setText(tr(self._status_template, self.language).format(**self._status_values))

    def set_manager(self, seller_manager) -> None:
        self.seller_manager = seller_manager
        self.refresh_sellers()

    def refresh_sellers(self) -> None:
        selected = self.seller_combo.currentData()
        self._profiles = self.seller_manager.list_all() if self.seller_manager else []
        self.seller_combo.clear()
        self.seller_combo.addItem(tr("All sellers", self.language), None)
        for profile in self._profiles:
            self.seller_combo.addItem(
                f"{profile.display_tag} ({profile.seller_id})",
                profile.seller_id,
            )
        index = self.seller_combo.findData(selected)
        if index >= 0:
            self.seller_combo.setCurrentIndex(index)
        self._update_enabled()

    def _set_status(self, template: str, **values: Any) -> None:
        self._status_template = template
        self._status_values = values
        self.status_label.setText(tr(template, self.language).format(**values))

    def fetch_orders(self) -> None:
        if self._worker is not None:
            return
        if not self._profiles:
            QMessageBox.information(
                self,
                tr("Fetch orders", self.language),
                tr("No seller profiles are configured.", self.language),
            )
            return

        start_day = datetime.strptime(
            self.start_date_input.date().toString("yyyy-MM-dd"), "%Y-%m-%d"
        ).date()
        end_day = datetime.strptime(
            self.end_date_input.date().toString("yyyy-MM-dd"), "%Y-%m-%d"
        ).date()
        if start_day > end_day:
            QMessageBox.warning(
                self,
                tr("Invalid date range", self.language),
                tr("The start date must be on or before the end date.", self.language),
            )
            return

        start_date = datetime.combine(start_day, time.min)
        end_date = datetime.combine(end_day + timedelta(days=1), time.min) - timedelta(
            milliseconds=1
        )
        self.order_table.setRowCount(0)
        self._set_status("Fetching orders for the selected date range...")
        worker = _FetchOrdersWorker(
            self._selected_profiles(),
            max_orders=self.max_orders_input.value(),
            start_date=start_date,
            end_date=end_date,
            all_statuses=True,
        )
        worker.completed.connect(self._on_orders_fetched)
        worker.log_emitted.connect(self.log_emitted)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self.operation_started.emit()
        self._update_enabled()
        worker.start()

    def _selected_profiles(self) -> List[SellerProfile]:
        seller_id = self.seller_combo.currentData()
        if seller_id is None:
            return list(self._profiles)
        return [profile for profile in self._profiles if profile.seller_id == seller_id]

    def _on_orders_fetched(
        self, result: Tuple[List[Dict[str, Any]], List[str]]
    ) -> None:
        packages, errors = result
        rows = _bookkeeping_rows(packages)
        self.order_table.setRowCount(0)
        for values in rows:
            row = self.order_table.rowCount()
            self.order_table.insertRow(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.order_table.setItem(row, column, item)

        self._loaded_order_count = len(packages)
        self._loaded_line_count = len(rows)
        self._set_status(
            "Loaded {orders} orders as {items} bookkeeping line(s).",
            orders=len(packages),
            items=len(rows),
        )
        self._apply_filter(self.search_input.text())
        if errors:
            QMessageBox.warning(
                self,
                tr("Some orders could not be fetched", self.language),
                "\n".join(errors),
            )

    def _apply_filter(self, query: str = "") -> None:
        normalized_query = query.strip().casefold()
        matching_rows = 0
        for row in range(self.order_table.rowCount()):
            row_text = " ".join(
                self.order_table.item(row, column).text()
                for column in range(self.order_table.columnCount())
                if self.order_table.item(row, column) is not None
            ).casefold()
            matches = not normalized_query or normalized_query in row_text
            self.order_table.setRowHidden(row, not matches)
            if matches:
                matching_rows += 1
            for column in range(self.order_table.columnCount()):
                item = self.order_table.item(row, column)
                if item is not None:
                    item.setBackground(
                        QColor("#134e4a") if normalized_query and matches else QColor()
                    )
        if normalized_query:
            self._set_status(
                "{matches} matching line(s) out of {total}.",
                matches=matching_rows,
                total=self._loaded_line_count,
            )
        elif self._loaded_order_count or self._loaded_line_count:
            self._set_status(
                "Loaded {orders} orders as {items} bookkeeping line(s).",
                orders=self._loaded_order_count,
                items=self._loaded_line_count,
            )

    def _on_worker_finished(self) -> None:
        self._worker = None
        self.operation_finished.emit()
        self._update_enabled()

    def _update_enabled(self) -> None:
        busy = self._worker is not None
        self.seller_combo.setEnabled(not busy and bool(self._profiles))
        self.start_date_input.setEnabled(not busy)
        self.end_date_input.setEnabled(not busy)
        self.max_orders_input.setEnabled(not busy)
        self.fetch_button.setEnabled(not busy and bool(self._profiles))
        self.search_input.setEnabled(not busy and self.order_table.rowCount() > 0)

    def stop_worker(self) -> bool:
        if self._worker is not None and self._worker.isRunning():
            return self._worker.wait(10_000)
        return True
