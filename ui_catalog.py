"""Product catalog management UI backed by the persistent ProductCatalog store."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.catalog import ProductCatalog, ProductItem
from core.config import get_config
from core.i18n import ask_yes_no, tr


class ProductEditor(QDialog):
    """Small add/edit dialog for one catalog product."""

    def __init__(
        self,
        parent=None,
        product: Optional[ProductItem] = None,
        language: str = "en",
    ):
        super().__init__(parent)
        self.language = language
        self.product = product
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.barcode = QLineEdit(product.barcode if product else "")
        self.display_name = QLineEdit(product.display_name if product else "")
        self.stock_code = QLineEdit(product.stock_code or "" if product else "")
        self.seller = QLineEdit(product.seller or "" if product else "")
        self.category = QLineEdit(product.category or "" if product else "")
        self.product_type = QLineEdit(product.product_type or "" if product else "")
        self.size_type = QComboBox()
        self.size_type.addItem("—", "")
        self.size_type.addItem("TEK", "TEK")
        self.size_type.addItem("ÇİFT", "ÇİFT")
        if product and product.size_type:
            idx = self.size_type.findData(product.size_type)
            if idx >= 0:
                self.size_type.setCurrentIndex(idx)
        self.notes = QLineEdit(product.notes or "" if product else "")

        self._field_labels = []
        for label, widget in (
            ("Barcode", self.barcode),
            ("Display name", self.display_name),
            ("Stock code", self.stock_code),
            ("Seller", self.seller),
            ("Category", self.category),
            ("Product type", self.product_type),
            ("Size type", self.size_type),
            ("Notes", self.notes),
        ):
            field_label = QLabel()
            self._field_labels.append((label, field_label))
            form.addRow(field_label, widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self._save_button = buttons.button(QDialogButtonBox.Save)
        self._cancel_button = buttons.button(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if product:
            self.barcode.setReadOnly(True)
        self.set_language(language)

    def set_language(self, language: str) -> None:
        self.language = language
        self.setWindowTitle(tr("Edit Product" if self.product else "Add Product", language))
        self.barcode.setPlaceholderText(tr("Required; unique product barcode", language))
        self.display_name.setPlaceholderText(tr("Product display name", language))
        for text, label in self._field_labels:
            label.setText(tr(text, language))
        self._save_button.setText(tr("Save", language))
        self._cancel_button.setText(tr("Cancel", language))
        if self.product:
            self.barcode.setToolTip(
                tr("Barcode is the catalog key and cannot be changed when editing.", language)
            )

    def product_item(self) -> ProductItem:
        return ProductItem(
            barcode=self.barcode.text().strip(),
            display_name=self.display_name.text().strip(),
            stock_code=self.stock_code.text().strip() or None,
            seller=self.seller.text().strip() or None,
            category=self.category.text().strip() or None,
            product_type=self.product_type.text().strip() or None,
            size_type=self.size_type.currentData() or None,
            notes=self.notes.text().strip() or None,
        )


class CatalogTab(QWidget):
    """Searchable, editable UI for the real on-disk product catalog."""

    HEADERS = ("Barcode", "Display Name", "Stock Code", "Seller", "Category", "Product Type", "Size")

    def __init__(self):
        super().__init__()
        self.language = "en"
        self.catalog = ProductCatalog(get_config().products_file)

        root_layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search barcode, name, stock code or seller...")
        self.search.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search, 1)

        self.seller_filter = QComboBox()
        self.seller_filter.addItem("All sellers", "")
        self.seller_filter.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self.seller_filter)

        self.btn_refresh = QPushButton()
        self.btn_add = QPushButton()
        self.btn_edit = QPushButton()
        self.btn_delete = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_add.clicked.connect(self.add_product)
        self.btn_edit.clicked.connect(self.edit_selected)
        self.btn_delete.clicked.connect(self.delete_selected)
        for button in (self.btn_refresh, self.btn_add, self.btn_edit, self.btn_delete):
            toolbar.addWidget(button)
        root_layout.addLayout(toolbar)

        self.summary = QLabel()
        root_layout.addWidget(self.summary)

        self.catalog_table = QTableWidget(0, len(self.HEADERS))
        self.catalog_table.setHorizontalHeaderLabels(list(self.HEADERS))
        self.catalog_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.catalog_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.catalog_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.catalog_table.setAlternatingRowColors(True)
        self.catalog_table.verticalHeader().setVisible(False)
        self.catalog_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.catalog_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.catalog_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.catalog_table.itemDoubleClicked.connect(lambda *_: self.edit_selected())
        root_layout.addWidget(self.catalog_table, 1)

        self.set_language(self.language)

    def set_language(self, language: str) -> None:
        self.language = language if language in ("en", "tr") else "en"
        self.search.setPlaceholderText(
            tr("Search barcode, name, stock code or seller...", self.language)
        )
        self.btn_refresh.setText(tr("Refresh", self.language))
        self.btn_add.setText(tr("Add Product", self.language))
        self.btn_edit.setText(tr("Edit Selected", self.language))
        self.btn_delete.setText(tr("Delete Selected", self.language))
        self.catalog_table.setHorizontalHeaderLabels(
            [tr(header, self.language) for header in self.HEADERS]
        )
        self.refresh()

    def _selected_barcode(self) -> Optional[str]:
        rows = self.catalog_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.catalog_table.item(rows[0].row(), 0)
        return item.text() if item else None

    def _filtered_products(self):
        query = self.search.text().strip().casefold()
        seller = self.seller_filter.currentData()
        products = self.catalog.list_all()
        return [
            product for product in products
            if (not seller or (product.seller or "") == seller)
            and (
                not query
                or query in " ".join(str(value or "") for value in (
                    product.barcode, product.display_name, product.stock_code,
                    product.seller, product.category, product.product_type,
                )).casefold()
            )
        ]

    def refresh(self, *_):
        products = self.catalog.list_all()
        selected_seller = self.seller_filter.currentData()
        sellers = sorted({p.seller for p in products if p.seller}, key=str.casefold)
        self.seller_filter.blockSignals(True)
        self.seller_filter.clear()
        self.seller_filter.addItem(tr("All sellers", self.language), "")
        for seller in sellers:
            self.seller_filter.addItem(seller, seller)
        idx = self.seller_filter.findData(selected_seller)
        self.seller_filter.setCurrentIndex(max(0, idx))
        self.seller_filter.blockSignals(False)

        visible = self._filtered_products()
        self.catalog_table.setRowCount(0)
        for row_idx, product in enumerate(visible):
            values = (
                product.barcode, product.display_name, product.stock_code or "",
                product.seller or "", product.category or "", product.product_type or "",
                product.size_type or "",
            )
            self.catalog_table.insertRow(row_idx)
            for col_idx, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col_idx == 0:
                    cell.setData(Qt.UserRole, product.barcode)
                self.catalog_table.setItem(row_idx, col_idx, cell)
        self.summary.setText(
            tr("{visible} products shown · {total} total", self.language).format(
                visible=len(visible),
                total=len(products),
            )
        )
        self.btn_edit.setEnabled(bool(visible))
        self.btn_delete.setEnabled(bool(visible))

    def add_product(self):
        dialog = ProductEditor(self, language=self.language)
        if dialog.exec() != QDialog.Accepted:
            return
        item = dialog.product_item()
        if not item.barcode or not item.display_name:
            QMessageBox.warning(
                self,
                tr("Missing information", self.language),
                tr("Barcode and display name are required.", self.language),
            )
            return
        try:
            self.catalog.add_or_update(item)
            self.refresh()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                tr("Catalog save failed", self.language),
                str(exc),
            )

    def edit_selected(self):
        barcode = self._selected_barcode()
        if not barcode:
            return
        existing = self.catalog.get_by_barcode(barcode)
        if existing is None:
            self.refresh()
            return
        dialog = ProductEditor(self, existing, language=self.language)
        if dialog.exec() != QDialog.Accepted:
            return
        item = dialog.product_item()
        if not item.display_name:
            QMessageBox.warning(
                self,
                tr("Missing information", self.language),
                tr("Display name is required.", self.language),
            )
            return
        try:
            self.catalog.add_or_update(item)
            self.refresh()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                tr("Catalog save failed", self.language),
                str(exc),
            )

    def delete_selected(self):
        barcode = self._selected_barcode()
        if not barcode:
            return
        answer = ask_yes_no(
            self,
            "Delete product",
            "Delete product {barcode} from the catalog?",
            self.language,
            barcode=barcode,
        )
        if not answer:
            return
        try:
            self.catalog.delete(barcode)
            self.refresh()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                tr("Catalog delete failed", self.language),
                str(exc),
            )

    # Kept as a compatibility method for older callers.
    def load_master_catalog(self, db_rows):
        self.catalog_table.setRowCount(0)
        for row_data in db_rows:
            row_idx = self.catalog_table.rowCount()
            self.catalog_table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data[:self.catalog_table.columnCount()]):
                self.catalog_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

    def apply_seller_overrides(self, overrides_dict):
        # Seller-specific overrides are not yet represented in the persistent catalog schema.
        return
