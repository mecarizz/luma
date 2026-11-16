"""Live Trendyol stock lookup and quantity updates."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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

from core.catalog import ProductCatalog, normalize_identifier
from core.i18n import tr
from core.logger import get_logger
from core.paths import get_data_path
from core.seller_models import SellerProfile
from core.trendyol_inventory import (
    MAX_UPDATE_ITEMS,
    MAX_SELLABLE_QUANTITY,
    InventoryProduct,
    InventoryUpdateResult,
    fetch_inventory,
    update_inventory,
)
from ui_components import SearchInput, SectionHeader


class _StockWorker(QThread):
    completed = Signal(str, object)
    failed = Signal(str, str)

    def __init__(
        self,
        operation: str,
        profile: SellerProfile,
        updates: Optional[Iterable[Dict[str, object]]] = None,
    ):
        super().__init__()
        self.operation = operation
        self.profile = profile
        self.updates = list(updates or [])

    def run(self) -> None:
        logger = get_logger()
        try:
            if self.operation == "fetch":
                logger.info("Stock lookup started: seller=%s", self.profile.display_tag)
                result = fetch_inventory(self.profile)
                logger.info(
                    "Stock lookup completed: seller=%s products=%d",
                    self.profile.display_tag,
                    len(result),
                )
            elif self.operation == "update":
                logger.info(
                    "Stock update started: seller=%s products=%d",
                    self.profile.display_tag,
                    len(self.updates),
                )
                result = update_inventory(self.profile, self.updates)
            else:
                raise ValueError(f"Unknown stock operation: {self.operation}")
            self.completed.emit(self.operation, result)
        except Exception as exc:
            logger.error(
                "Stock %s failed for seller %s: %s",
                self.operation,
                self.profile.display_tag,
                exc,
            )
            self.failed.emit(self.operation, str(exc))


class StockTab(QWidget):
    operation_started = Signal()
    operation_finished = Signal()

    HEADERS = ("Barcode", "Product", "Seller SKU", "Trendyol stock", "New stock")

    def __init__(self):
        super().__init__()
        self.language = "en"
        self.seller_manager = None
        self._profiles: List[SellerProfile] = []
        self._inventory: List[InventoryProduct] = []
        self._worker: Optional[_StockWorker] = None
        self._writing = False
        self._refresh_after_worker = False
        self._pending_result = False
        self._status_template = "Select a seller and fetch live inventory."
        self._status_values: Dict[str, Any] = {}
        self.catalog = ProductCatalog(str(get_data_path("products.json")))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.header = SectionHeader(
            title="Stock Management",
            subtitle="View and update live Trendyol stock quantities for one seller.",
        )
        layout.addWidget(self.header)

        controls_card = QFrame()
        controls_card.setObjectName("panel")
        controls_layout = QHBoxLayout(controls_card)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(12)

        self.seller_label = QLabel("Seller:")
        self.seller_combo = QComboBox()
        self.seller_combo.setMinimumWidth(220)
        self.seller_combo.currentIndexChanged.connect(self._on_seller_changed)

        self.fetch_button = QPushButton("Fetch Stock")
        self.fetch_button.setObjectName("ghostButton")
        self.fetch_button.clicked.connect(self.refresh_inventory)

        self.apply_button = QPushButton("Apply Stock Changes")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.clicked.connect(self.apply_changes)

        controls_layout.addWidget(self.seller_label)
        controls_layout.addWidget(self.seller_combo)
        controls_layout.addWidget(self.fetch_button)
        controls_layout.addWidget(self.apply_button)
        controls_layout.addStretch()
        layout.addWidget(controls_card)

        self.search_input = SearchInput(
            placeholder="Filter by barcode, product, or seller SKU...",
            debounce_ms=150,
        )
        self.search_input.debounced_text_changed.connect(self._apply_filter)
        layout.addWidget(self.search_input)

        self.status_label = QLabel(self._status_template)
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
        layout.addWidget(self.status_label)

        self.inventory_table = QTableWidget(0, len(self.HEADERS))
        self.inventory_table.setHorizontalHeaderLabels(list(self.HEADERS))
        self.inventory_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.inventory_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.inventory_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.inventory_table.setAlternatingRowColors(True)
        self.inventory_table.verticalHeader().setVisible(False)
        self.inventory_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.inventory_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.inventory_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.inventory_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.inventory_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        layout.addWidget(self.inventory_table, 1)

        self.set_language("en")
        self._update_enabled()

    def set_language(self, language: str) -> None:
        self.language = language if language in ("en", "tr") else "en"
        self.header.set_language(self.language)
        self.seller_label.setText(tr("Seller:", self.language))
        self.fetch_button.setText(tr("Fetch Stock", self.language))
        self.apply_button.setText(tr("Apply Stock Changes", self.language))
        self.search_input.setPlaceholderText(
            tr("Filter by barcode, product, or seller SKU...", self.language)
        )
        self.inventory_table.setHorizontalHeaderLabels(
            [tr(header, self.language) for header in self.HEADERS]
        )
        self.status_label.setText(
            tr(self._status_template, self.language).format(**self._status_values)
        )

    def set_manager(self, seller_manager) -> None:
        self.seller_manager = seller_manager
        self.refresh_sellers()

    def refresh_sellers(self) -> None:
        selected_seller = self.seller_combo.currentData()
        if self.seller_manager is None:
            self._profiles = []
        else:
            self._profiles = self.seller_manager.list_all()

        self.seller_combo.blockSignals(True)
        self.seller_combo.clear()
        for profile in self._profiles:
            self.seller_combo.addItem(
                f"{profile.display_tag} ({profile.seller_id})",
                profile.seller_id,
            )
        selected_index = self.seller_combo.findData(selected_seller)
        if selected_index >= 0:
            self.seller_combo.setCurrentIndex(selected_index)
        self.seller_combo.blockSignals(False)
        self._clear_inventory()
        if self._profiles:
            self._set_status("Select a seller and fetch live inventory.")
        else:
            self._set_status("No seller profiles are configured.")
        self._update_enabled()

    def _selected_profile(self) -> Optional[SellerProfile]:
        seller_id = self.seller_combo.currentData()
        return next(
            (profile for profile in self._profiles if profile.seller_id == seller_id),
            None,
        )

    def _set_status(self, template: str, **values: Any) -> None:
        self._status_template = template
        self._status_values = values
        self.status_label.setText(
            tr(template, self.language).format(**values)
        )

    def _clear_inventory(self) -> None:
        self._inventory = []
        self.inventory_table.setRowCount(0)
        self._pending_result = False

    def _on_seller_changed(self, *_args) -> None:
        self._clear_inventory()
        self._set_status("Seller changed. Fetch inventory to continue.")
        self._update_enabled()

    def refresh_inventory(self) -> None:
        if self._worker is not None:
            return
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.information(
                self,
                tr("Stock Management", self.language),
                tr("No seller profiles are configured.", self.language),
            )
            return
        self._clear_inventory()
        self._set_status("Fetching live inventory for {seller}...", seller=profile.display_tag)
        self._start_worker(_StockWorker("fetch", profile))

    def _start_worker(self, worker: _StockWorker, writing: bool = False) -> None:
        self._worker = worker
        self._writing = writing
        worker.completed.connect(self._on_worker_completed)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_worker_finished)
        self._update_enabled()
        if writing:
            self.operation_started.emit()
        worker.start()

    def _on_worker_completed(self, operation: str, result: object) -> None:
        if operation == "fetch":
            if not isinstance(result, list) or not all(
                isinstance(item, InventoryProduct) for item in result
            ):
                self._set_status("Trendyol returned an invalid inventory list.")
                return
            self._inventory = result
            self._pending_result = False
            self._render_inventory()
            profile = self._selected_profile()
            self._set_status(
                "Loaded {count} products for {seller}.",
                count=len(result),
                seller=profile.display_tag if profile else "",
            )
            return

        if not isinstance(result, InventoryUpdateResult):
            self._set_status("Trendyol returned an invalid stock update result.")
            return
        successful = len(result.successful_barcodes)
        failures = len(result.failures)
        pending = len(result.pending_barcodes)
        self._pending_result = pending > 0
        if pending:
            self._refresh_after_worker = False
            if result.status_error:
                self._set_status(
                    "Batch {batch} was submitted, but status could not be checked: {error}",
                    batch=result.batch_request_id,
                    error=result.status_error,
                )
                message = tr(
                    "The stock update was submitted, but Trendyol's result could not be checked. Refresh inventory before retrying. Batch: {batch}\n\n{error}",
                    self.language,
                ).format(batch=result.batch_request_id, error=result.status_error)
            else:
                self._set_status(
                    "{success} updated, {failed} failed, {pending} still processing. Batch: {batch}",
                    success=successful,
                    failed=failures,
                    pending=pending,
                    batch=result.batch_request_id,
                )
                message = tr(
                    "Trendyol is still processing some stock changes. Refresh the inventory before retrying. Batch: {batch}",
                    self.language,
                ).format(batch=result.batch_request_id)
            QMessageBox.warning(
                self,
                tr("Stock update pending", self.language),
                message,
            )
        elif failures:
            failure_details = "\n".join(
                f"{barcode}: {reason}" for barcode, reason in result.failures[:8]
            )
            self._set_status(
                "{success} updated and {failed} failed. Batch: {batch}",
                success=successful,
                failed=failures,
                batch=result.batch_request_id,
            )
            QMessageBox.warning(
                self,
                tr("Stock update results", self.language),
                tr(
                    "Updated: {success}\nFailed: {failed}\n{details}\nBatch: {batch}",
                    self.language,
                ).format(
                    success=successful,
                    failed=failures,
                    details=failure_details,
                    batch=result.batch_request_id,
                ),
            )
            self._refresh_after_worker = True
        else:
            self._set_status(
                "Updated stock for {count} products. Batch: {batch}",
                count=successful,
                batch=result.batch_request_id,
            )
            QMessageBox.information(
                self,
                tr("Stock update complete", self.language),
                tr(
                    "Updated stock for {count} products in Trendyol.",
                    self.language,
                ).format(count=successful),
            )
            self._refresh_after_worker = True

    def _on_worker_failed(self, operation: str, error: str) -> None:
        if operation == "update":
            self._pending_result = True
            self._refresh_after_worker = False
            self._set_status(
                "Stock update failed or may still be pending. Refresh inventory before retrying: {error}",
                error=error,
            )
        else:
            self._set_status(
                "Stock {operation} failed: {error}",
                operation=operation,
                error=error,
            )
        QMessageBox.critical(
            self,
            tr("Stock operation failed", self.language),
            tr(
                "Refresh live inventory before trying another stock update.\n\n{error}",
                self.language,
            ).format(error=error)
            if operation == "update"
            else error,
        )

    def _on_worker_finished(self) -> None:
        self._worker = None
        was_writing = self._writing
        self._writing = False
        self._update_enabled()
        if was_writing:
            self.operation_finished.emit()
        if self._refresh_after_worker:
            self._refresh_after_worker = False
            self.refresh_inventory()

    def _render_inventory(self) -> None:
        catalog_products = self.catalog.list_all()
        catalog_by_barcode = {
            normalize_identifier(item.barcode): item for item in catalog_products
        }
        catalog_by_stock_code: Dict[str, List[Any]] = {}
        for item in catalog_products:
            stock_code = normalize_identifier(item.stock_code)
            if stock_code:
                catalog_by_stock_code.setdefault(stock_code, []).append(item)

        profile = self._selected_profile()
        seller_name = profile.name.strip().casefold() if profile else ""
        self.inventory_table.setRowCount(0)
        for product in self._inventory:
            catalog_product = catalog_by_barcode.get(
                normalize_identifier(product.barcode)
            )
            if not catalog_product and product.stock_code:
                candidates = catalog_by_stock_code.get(
                    normalize_identifier(product.stock_code), []
                )
                seller_matches = [
                    item
                    for item in candidates
                    if seller_name and (item.seller or "").strip().casefold() == seller_name
                ]
                if len(seller_matches) == 1:
                    catalog_product = seller_matches[0]
                elif len(candidates) == 1:
                    catalog_product = candidates[0]
            display_name = (
                catalog_product.display_name
                if catalog_product and catalog_product.display_name.strip()
                else product.title.strip() or tr("Unknown", self.language)
            )
            row = self.inventory_table.rowCount()
            self.inventory_table.insertRow(row)
            values = (
                product.barcode,
                display_name,
                product.stock_code,
                str(product.quantity)
                if product.quantity is not None
                else tr("Unknown", self.language),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if column == 1:
                    cell.setToolTip(display_name)
                self.inventory_table.setItem(row, column, cell)

            quantity_input = QSpinBox()
            quantity_input.setRange(0, MAX_SELLABLE_QUANTITY)
            quantity_input.setMinimumWidth(112)
            quantity_input.setMaximumWidth(132)
            quantity_input.setAlignment(Qt.AlignCenter)
            quantity_input.setStyleSheet(
                "QSpinBox { background-color: #0f172a; color: #f8fafc; "
                "border: 1px solid #2a3b54; border-radius: 6px; padding: 2px 6px; "
                "selection-background-color: #0d9488; selection-color: #ffffff; }"
                "QSpinBox:focus { border: 2px solid #2dd4bf; "
                "background-color: #111c2e; color: #ffffff; }"
                "QSpinBox:disabled { color: #64748b; background-color: #0b1120; "
                "border-color: #1e293b; }"
            )
            if product.quantity is None or not 0 <= product.quantity <= MAX_SELLABLE_QUANTITY:
                quantity_input.setValue(0)
                quantity_input.setEnabled(False)
            else:
                quantity_input.setValue(product.quantity)
                quantity_input.valueChanged.connect(self._update_enabled)
            self.inventory_table.setCellWidget(row, 4, quantity_input)
        self._apply_filter()
        self._update_enabled()

    def _apply_filter(self, *_args) -> None:
        query = self.search_input.text().strip().casefold()
        for row in range(self.inventory_table.rowCount()):
            row_text = " ".join(
                self.inventory_table.item(row, column).text()
                for column in range(4)
                if self.inventory_table.item(row, column)
            ).casefold()
            self.inventory_table.setRowHidden(row, bool(query) and query not in row_text)

    def _pending_changes(self) -> List[Dict[str, object]]:
        changes = []
        for row, product in enumerate(self._inventory):
            if product.quantity is None:
                continue
            quantity_input = self.inventory_table.cellWidget(row, 4)
            if not isinstance(quantity_input, QSpinBox):
                continue
            if quantity_input.value() != product.quantity:
                changes.append(
                    {"barcode": product.barcode, "quantity": quantity_input.value()}
                )
        return changes

    def apply_changes(self) -> None:
        if self._worker is not None or self._pending_result:
            return
        profile = self._selected_profile()
        changes = self._pending_changes()
        if profile is None or not changes:
            return
        if len(changes) > MAX_UPDATE_ITEMS:
            QMessageBox.warning(
                self,
                tr("Too many stock changes", self.language),
                tr(
                    "Select no more than 1000 stock changes at a time.",
                    self.language,
                ),
            )
            return

        current_quantities = {
            product.barcode: product.quantity for product in self._inventory
        }
        change_summary = "\n".join(
            f"{item['barcode']}: {current_quantities[item['barcode']]} -> {item['quantity']}"
            for item in changes[:10]
        )
        if len(changes) > 10:
            change_summary += f"\n... {len(changes) - 10} more"
        prompt = tr(
            "Apply {count} live stock changes to {seller}?\n\n{changes}\n\nRefresh first if inventory changed outside Luma. This changes Trendyol inventory only; Luma's local product catalog is not changed.",
            self.language,
        ).format(
            count=len(changes),
            seller=profile.display_tag,
            changes=change_summary,
        )
        answer = QMessageBox.question(
            self,
            tr("Confirm stock update", self.language),
            prompt,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self._refresh_after_worker = False
        self._start_worker(_StockWorker("update", profile, changes), writing=True)

    def _update_enabled(self, *_args) -> None:
        busy = self._worker is not None
        has_seller = self._selected_profile() is not None
        self.seller_combo.setEnabled(not busy and has_seller)
        self.fetch_button.setEnabled(not busy and has_seller)
        self.apply_button.setEnabled(
            not busy
            and has_seller
            and not self._pending_result
            and bool(self._pending_changes())
        )
        self.search_input.setEnabled(bool(self._inventory))
