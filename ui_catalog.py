"""Product catalog management UI backed by the persistent ProductCatalog store and OutsourcedClassifier."""
from __future__ import annotations

import csv
import fnmatch
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.catalog import ProductCatalog, ProductItem
from core.classifier import OutsourcedClassifier
from core.config import get_config
from core.i18n import ask_yes_no, tr
from core.paths import get_data_path
from ui_components import EmptyStateWidget, SearchInput, SectionHeader, StatusBadge


class ProductEditor(QDialog):
    """Modern add/edit dialog for one catalog product with outsourced routing flag."""

    def __init__(
        self,
        parent=None,
        product: Optional[ProductItem] = None,
        is_outsourced: bool = False,
        language: str = "en",
    ):
        super().__init__(parent)
        self.language = language
        self.product = product
        self.setMinimumWidth(500)
        self.setStyleSheet("background-color: #111827; color: #f8fafc;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        title_label = QLabel("Edit Product" if product else "Add New Product")
        title_label.setObjectName("sectionTitle")
        main_layout.addWidget(title_label)

        form = QFormLayout()
        form.setSpacing(10)

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

        self.is_outsourced_cb = QCheckBox("Forward to external partner (Outsourced product)")
        self.is_outsourced_cb.setChecked(is_outsourced)
        self.is_outsourced_cb.setStyleSheet("color: #f59e0b; font-weight: 600;")

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
            ("Fulfillment", self.is_outsourced_cb),
        ):
            field_label = QLabel()
            field_label.setStyleSheet("color: #cbd5e1; font-weight: 600;")
            self._field_labels.append((label, field_label))
            form.addRow(field_label, widget)

        main_layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self._save_button = buttons.button(QDialogButtonBox.Save)
        self._save_button.setObjectName("primaryButton")
        self._cancel_button = buttons.button(QDialogButtonBox.Cancel)
        self._cancel_button.setObjectName("ghostButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        if product:
            self.barcode.setReadOnly(True)
        self.set_language(language)

    def set_language(self, language: str) -> None:
        self.language = language
        self.setWindowTitle(tr("Edit Product" if self.product else "Add Product", language))
        self.barcode.setPlaceholderText(tr("Required; unique product barcode", language))
        self.display_name.setPlaceholderText(tr("Product display name", language))
        self.is_outsourced_cb.setText(tr("Forward to external partner (Outsourced product)", language))
        for text, label in self._field_labels:
            label.setText(tr(text, language))
        self._save_button.setText(tr("Save", language))
        self._cancel_button.setText(tr("Cancel", language))
        if self.product:
            self.barcode.setToolTip(
                tr("Barcode is the catalog key and cannot be changed when editing.", language)
            )

    def is_outsourced(self) -> bool:
        return self.is_outsourced_cb.isChecked()

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
    """Searchable, editable UI for product catalog and outsourced products routing."""

    HEADERS = ("Barcode", "Display Name", "Stock Code", "Seller", "Category", "Product Type", "Size", "Fulfillment")
    RULES_HEADERS = ("Rule / Pattern", "Rule Type", "Catalog Matches", "Status", "Action")

    def __init__(self):
        super().__init__()
        self.language = "en"
        self.catalog = ProductCatalog(get_config().products_file)
        self.classifier = OutsourcedClassifier(str(get_data_path("outsourced_products.txt")))

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(14)

        # Header
        self.header = SectionHeader(
            title="Product Catalog",
            subtitle="Search, maintain, and categorize products for thermal label printing or partner outsourcing.",
        )
        root_layout.addWidget(self.header)

        # Segmented Sub-Navigation Switcher
        nav_card = QFrame()
        nav_card.setObjectName("panel")
        nav_layout = QHBoxLayout(nav_card)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(8)

        self.btn_tab_master = QPushButton("📦 Master Catalog")
        self.btn_tab_master.setCursor(Qt.PointingHandCursor)
        self.btn_tab_master.clicked.connect(lambda: self._set_subpage(0))

        self.btn_tab_outsourced = QPushButton("🏷️ Outsourced Products")
        self.btn_tab_outsourced.setCursor(Qt.PointingHandCursor)
        self.btn_tab_outsourced.clicked.connect(lambda: self._set_subpage(1))

        nav_layout.addWidget(self.btn_tab_master)
        nav_layout.addWidget(self.btn_tab_outsourced)
        nav_layout.addStretch()
        root_layout.addWidget(nav_card)

        # Stacked Views (0 = Master Catalog, 1 = Outsourced Products)
        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)

        # Build Sub-Pages
        self._build_master_catalog_page()
        self._build_outsourced_page()

        self._current_subpage = 0
        self._update_tab_button_styles()
        self.set_language(self.language)

    def _set_subpage(self, index: int) -> None:
        self._current_subpage = index
        self.stack.setCurrentIndex(index)
        self._update_tab_button_styles()
        if index == 0:
            self.refresh()
        else:
            self.refresh_rules()

    def _update_tab_button_styles(self) -> None:
        active_style = (
            "QPushButton { background-color: #162032; color: #14b8a6; border: 1px solid #14b8a6; "
            "border-radius: 6px; padding: 7px 18px; font-weight: 700; font-size: 9.5pt; }"
        )
        inactive_style = (
            "QPushButton { background-color: transparent; color: #94a3b8; border: 1px solid transparent; "
            "border-radius: 6px; padding: 7px 18px; font-weight: 500; font-size: 9.5pt; } "
            "QPushButton:hover { background-color: #1f293d; color: #f8fafc; }"
        )
        if self._current_subpage == 0:
            self.btn_tab_master.setStyleSheet(active_style)
            self.btn_tab_outsourced.setStyleSheet(inactive_style)
        else:
            self.btn_tab_master.setStyleSheet(inactive_style)
            self.btn_tab_outsourced.setStyleSheet(active_style)

    # -------------------------------------------------------------------------
    # Page 0: Master Catalog
    # -------------------------------------------------------------------------
    def _build_master_catalog_page(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(12)

        # Toolbar Card
        toolbar_card = QFrame()
        toolbar_card.setObjectName("panel")
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(14, 12, 14, 12)
        toolbar.setSpacing(10)

        self.search = SearchInput(placeholder="Search barcode, name, stock code or seller...", debounce_ms=150)
        self.search.debounced_text_changed.connect(self.refresh)
        toolbar.addWidget(self.search, 2)

        self.seller_filter = QComboBox()
        self.seller_filter.addItem("All sellers", "")
        self.seller_filter.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self.seller_filter, 1)

        self.size_filter = QComboBox()
        self.size_filter.addItem("All sizes", "")
        self.size_filter.addItem("TEK", "TEK")
        self.size_filter.addItem("ÇİFT", "ÇİFT")
        self.size_filter.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self.size_filter)

        self.fulfillment_filter = QComboBox()
        self.fulfillment_filter.addItem("All fulfillment", "")
        self.fulfillment_filter.addItem("In-House only", "in_house")
        self.fulfillment_filter.addItem("Outsourced only", "outsourced")
        self.fulfillment_filter.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self.fulfillment_filter)

        self.btn_refresh = QPushButton()
        self.btn_refresh.setObjectName("ghostButton")
        self.btn_add = QPushButton()
        self.btn_add.setObjectName("primaryButton")
        self.btn_edit = QPushButton()
        self.btn_toggle_outsourced = QPushButton("Toggle Outsourced")
        self.btn_toggle_outsourced.setObjectName("ghostButton")
        self.btn_delete = QPushButton()
        self.btn_delete.setObjectName("destructiveButton")
        self.btn_export = QPushButton("Export CSV")
        self.btn_export.setObjectName("ghostButton")

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_add.clicked.connect(self.add_product)
        self.btn_edit.clicked.connect(self.edit_selected)
        self.btn_toggle_outsourced.clicked.connect(self.toggle_outsourced_selected)
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_export.clicked.connect(self.export_csv)

        for button in (
            self.btn_add,
            self.btn_edit,
            self.btn_toggle_outsourced,
            self.btn_delete,
            self.btn_export,
            self.btn_refresh,
        ):
            toolbar.addWidget(button)

        page_layout.addWidget(toolbar_card)

        # Summary strip
        summary_row = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
        self.badge_count = StatusBadge("0 Products", "info")
        self.badge_outsourced_count = StatusBadge("0 Outsourced", "warning")

        summary_row.addWidget(self.summary, 1)
        summary_row.addWidget(self.badge_outsourced_count)
        summary_row.addWidget(self.badge_count)
        page_layout.addLayout(summary_row)

        # Catalog Table
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
        self.catalog_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.catalog_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.catalog_table.itemDoubleClicked.connect(lambda *_: self.edit_selected())
        page_layout.addWidget(self.catalog_table, 1)

        self.stack.addWidget(page)

    # -------------------------------------------------------------------------
    # Page 1: Outsourced Products Management
    # -------------------------------------------------------------------------
    def _build_outsourced_page(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(12)

        # Top Controls: Add Rule + Test Rule side by side
        top_cards = QHBoxLayout()
        top_cards.setSpacing(12)

        # 1. Add Rule Card
        card_add = QFrame()
        card_add.setObjectName("panel")
        layout_add = QVBoxLayout(card_add)
        layout_add.setContentsMargins(14, 12, 14, 12)
        layout_add.setSpacing(8)

        lbl_add_title = QLabel("Add Outsourced Barcode or Wildcard")
        lbl_add_title.setStyleSheet("font-weight: 700; color: #f8fafc; font-size: 10pt;")
        self.lbl_add_sub = QLabel(
            "Barcodes matching these rules will not be printed locally; they are saved to PDF for supplier forwarding."
        )
        self.lbl_add_sub.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")

        row_add = QHBoxLayout()
        self.input_new_rule = QLineEdit()
        self.input_new_rule.setPlaceholderText("Enter barcode or prefix wildcard (e.g. AYKK* or 868...)...")
        self.input_new_rule.returnPressed.connect(self.add_outsourced_rule)

        self.btn_add_rule = QPushButton("Add to Outsourced")
        self.btn_add_rule.setObjectName("primaryButton")
        self.btn_add_rule.setCursor(Qt.PointingHandCursor)
        self.btn_add_rule.clicked.connect(self.add_outsourced_rule)

        row_add.addWidget(self.input_new_rule, 1)
        row_add.addWidget(self.btn_add_rule)

        layout_add.addWidget(lbl_add_title)
        layout_add.addWidget(self.lbl_add_sub)
        layout_add.addLayout(row_add)
        top_cards.addWidget(card_add, 1)

        # 2. Rule Tester Card
        card_test = QFrame()
        card_test.setObjectName("panel")
        layout_test = QVBoxLayout(card_test)
        layout_test.setContentsMargins(14, 12, 14, 12)
        layout_test.setSpacing(8)

        lbl_test_title = QLabel("Barcode Routing Tester")
        lbl_test_title.setStyleSheet("font-weight: 700; color: #f8fafc; font-size: 10pt;")
        self.lbl_test_sub = QLabel(
            "Quickly test a barcode to verify whether it matches any active outsourced forwarding rule."
        )
        self.lbl_test_sub.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")

        row_test = QHBoxLayout()
        self.input_test_barcode = QLineEdit()
        self.input_test_barcode.setPlaceholderText("Test barcode lookup (e.g. AYKK1234)...")
        self.input_test_barcode.returnPressed.connect(self.test_barcode_match)

        self.btn_test_barcode = QPushButton("Check Match")
        self.btn_test_barcode.setObjectName("ghostButton")
        self.btn_test_barcode.setCursor(Qt.PointingHandCursor)
        self.btn_test_barcode.clicked.connect(self.test_barcode_match)

        row_test.addWidget(self.input_test_barcode, 1)
        row_test.addWidget(self.btn_test_barcode)

        self.lbl_test_result = QLabel("Enter a barcode above to test fulfillment routing.")
        self.lbl_test_result.setStyleSheet("color: #94a3b8; font-size: 8.5pt; font-style: italic;")

        layout_test.addWidget(lbl_test_title)
        layout_test.addWidget(self.lbl_test_sub)
        layout_test.addLayout(row_test)
        layout_test.addWidget(self.lbl_test_result)
        top_cards.addWidget(card_test, 1)

        page_layout.addLayout(top_cards)

        # Rules Toolbar
        rules_toolbar_card = QFrame()
        rules_toolbar_card.setObjectName("panel")
        rules_toolbar = QHBoxLayout(rules_toolbar_card)
        rules_toolbar.setContentsMargins(14, 10, 14, 10)
        rules_toolbar.setSpacing(10)

        self.search_rules = SearchInput(placeholder="Filter outsourced rules...", debounce_ms=100)
        self.search_rules.debounced_text_changed.connect(self.refresh_rules)
        rules_toolbar.addWidget(self.search_rules, 2)

        self.btn_remove_rule = QPushButton("Remove Selected Rule")
        self.btn_remove_rule.setObjectName("destructiveButton")
        self.btn_remove_rule.setCursor(Qt.PointingHandCursor)
        self.btn_remove_rule.clicked.connect(self.remove_selected_rule)

        self.btn_validate_rules = QPushButton("Validate Rules")
        self.btn_validate_rules.setObjectName("ghostButton")
        self.btn_validate_rules.setCursor(Qt.PointingHandCursor)
        self.btn_validate_rules.clicked.connect(self.validate_rules)

        self.btn_open_outsourced_folder = QPushButton("Open Outsourced Folder")
        self.btn_open_outsourced_folder.setObjectName("ghostButton")
        self.btn_open_outsourced_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_outsourced_folder.clicked.connect(self.open_outsourced_folder)

        self.btn_export_rules = QPushButton("Export Rules")
        self.btn_export_rules.setObjectName("ghostButton")
        self.btn_export_rules.setCursor(Qt.PointingHandCursor)
        self.btn_export_rules.clicked.connect(self.export_rules)

        self.btn_import_rules = QPushButton("Import Rules")
        self.btn_import_rules.setObjectName("ghostButton")
        self.btn_import_rules.setCursor(Qt.PointingHandCursor)
        self.btn_import_rules.clicked.connect(self.import_rules)

        for btn in (
            self.btn_remove_rule,
            self.btn_validate_rules,
            self.btn_open_outsourced_folder,
            self.btn_export_rules,
            self.btn_import_rules,
        ):
            rules_toolbar.addWidget(btn)

        page_layout.addWidget(rules_toolbar_card)

        # Rules Summary Strip
        rules_summary_row = QHBoxLayout()
        self.lbl_rules_summary = QLabel()
        self.lbl_rules_summary.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
        self.badge_rules_count = StatusBadge("0 Rules", "warning")
        rules_summary_row.addWidget(self.lbl_rules_summary, 1)
        rules_summary_row.addWidget(self.badge_rules_count)
        page_layout.addLayout(rules_summary_row)

        # Rules Table
        self.rules_table = QTableWidget(0, len(self.RULES_HEADERS))
        self.rules_table.setHorizontalHeaderLabels(list(self.RULES_HEADERS))
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rules_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.rules_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.verticalHeader().setVisible(False)
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.rules_table.itemDoubleClicked.connect(lambda *_: self.remove_selected_rule())
        page_layout.addWidget(self.rules_table, 1)

        self.stack.addWidget(page)

    # -------------------------------------------------------------------------
    # Localization
    # -------------------------------------------------------------------------
    def set_language(self, language: str) -> None:
        self.language = language if language in ("en", "tr") else "en"
        self.header.set_language(self.language)
        self.btn_tab_master.setText(f"📦 {tr('Master Catalog', self.language)}")
        self.btn_tab_outsourced.setText(f"🏷️ {tr('Outsourced Products', self.language)}")

        # Master page texts
        self.search.setPlaceholderText(
            tr("Search barcode, name, stock code or seller...", self.language)
        )
        self.seller_filter.setItemText(0, tr("All sellers", self.language))
        self.size_filter.setItemText(0, tr("All sizes", self.language))
        self.fulfillment_filter.setItemText(0, tr("All fulfillment", self.language))
        self.fulfillment_filter.setItemText(1, tr("In-House only", self.language))
        self.fulfillment_filter.setItemText(2, tr("Outsourced only", self.language))

        self.btn_refresh.setText(tr("Refresh", self.language))
        self.btn_add.setText(tr("Add Product", self.language))
        self.btn_edit.setText(tr("Edit Selected", self.language))
        self.btn_toggle_outsourced.setText(tr("Toggle Outsourced", self.language))
        self.btn_delete.setText(tr("Delete Selected", self.language))
        self.btn_export.setText(tr("Export CSV", self.language))
        self.catalog_table.setHorizontalHeaderLabels(
            [tr(header, self.language) for header in self.HEADERS]
        )

        # Outsourced page texts
        self.lbl_add_sub.setText(
            tr("Barcodes and wildcard rules forwarded to third-party suppliers instead of being printed locally.", self.language)
        )
        self.input_new_rule.setPlaceholderText(
            tr("Enter barcode or wildcard pattern (e.g. AYKK* or 868...)...", self.language)
        )
        self.btn_add_rule.setText(tr("Add to Outsourced", self.language))
        self.input_test_barcode.setPlaceholderText(tr("Test barcode lookup...", self.language))
        self.btn_test_barcode.setText(tr("Check Match", self.language))

        self.search_rules.setPlaceholderText(tr("Filter outsourced rules...", self.language))
        self.btn_remove_rule.setText(tr("Remove Selected Rule", self.language))
        self.btn_validate_rules.setText(tr("Validate Rules", self.language))
        self.btn_open_outsourced_folder.setText(tr("Open Outsourced Folder", self.language))
        self.btn_export_rules.setText(tr("Export Rules", self.language))
        self.btn_import_rules.setText(tr("Import Rules", self.language))
        self.rules_table.setHorizontalHeaderLabels(
            [tr(h, self.language) for h in self.RULES_HEADERS]
        )

        self.refresh()
        self.refresh_rules()

    # -------------------------------------------------------------------------
    # Master Catalog Methods
    # -------------------------------------------------------------------------
    def _selected_barcode(self) -> Optional[str]:
        rows = self.catalog_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.catalog_table.item(rows[0].row(), 0)
        return item.text() if item else None

    def _filtered_products(self) -> List[ProductItem]:
        query = self.search.text().strip().casefold()
        seller = self.seller_filter.currentData()
        size_type = self.size_filter.currentData()
        fulf_filter = self.fulfillment_filter.currentData()
        products = self.catalog.list_all()

        results = []
        for product in products:
            if seller and (product.seller or "") != seller:
                continue
            if size_type and (product.size_type or "") != size_type:
                continue
            is_out, _ = self.classifier.is_outsourced_barcode(product.barcode)
            if fulf_filter == "in_house" and is_out:
                continue
            if fulf_filter == "outsourced" and not is_out:
                continue
            if query:
                combined = " ".join(
                    str(value or "") for value in (
                        product.barcode, product.display_name, product.stock_code,
                        product.seller, product.category, product.product_type,
                    )
                ).casefold()
                if query not in combined:
                    continue
            results.append(product)
        return results

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
        outsourced_total = 0

        for row_idx, product in enumerate(visible):
            is_out, rule = self.classifier.is_outsourced_barcode(product.barcode)
            if is_out:
                outsourced_total += 1
                fulf_text = f"Outsourced ({rule})" if rule != product.barcode else "Outsourced"
                fulf_color = "#f59e0b"
            else:
                fulf_text = "In-House"
                fulf_color = "#14b8a6"

            values = (
                product.barcode,
                product.display_name,
                product.stock_code or "",
                product.seller or "",
                product.category or "",
                product.product_type or "",
                product.size_type or "",
                tr(fulf_text, self.language),
            )
            self.catalog_table.insertRow(row_idx)
            for col_idx, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col_idx == 0:
                    cell.setData(Qt.UserRole, product.barcode)
                elif col_idx == 7:
                    cell.setForeground(Qt.GlobalColor.white if is_out else Qt.GlobalColor.lightGray)
                    cell.setTextAlignment(Qt.AlignCenter)
                    cell.setData(Qt.UserRole, "outsourced" if is_out else "in_house")
                    cell.setToolTip(
                        tr("Outsourced to supplier", self.language) if is_out else tr("Thermal printed in-house", self.language)
                    )
                self.catalog_table.setItem(row_idx, col_idx, cell)

        self.summary.setText(
            tr("{visible} products shown · {total} total", self.language).format(
                visible=len(visible),
                total=len(products),
            )
        )
        self.badge_count.setText(f"{len(visible)} " + tr("Visible", self.language))
        self.badge_outsourced_count.setText(f"{outsourced_total} " + tr("Outsourced", self.language))
        self.btn_edit.setEnabled(bool(visible))
        self.btn_toggle_outsourced.setEnabled(bool(visible))
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
            if dialog.is_outsourced():
                self.classifier.add_pattern(item.barcode)
            self.refresh()
            self.refresh_rules()
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
        is_out, _ = self.classifier.is_outsourced_barcode(barcode)
        dialog = ProductEditor(self, existing, is_outsourced=is_out, language=self.language)
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
            if dialog.is_outsourced():
                self.classifier.add_pattern(item.barcode)
            elif is_out:
                self.classifier.remove_pattern(item.barcode)
            self.refresh()
            self.refresh_rules()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                tr("Catalog save failed", self.language),
                str(exc),
            )

    def toggle_outsourced_selected(self) -> None:
        """Toggle the outsourced fulfillment state for the selected product."""
        barcode = self._selected_barcode()
        if not barcode:
            return
        is_out, rule = self.classifier.is_outsourced_barcode(barcode)
        if is_out:
            if rule == barcode:
                self.classifier.remove_pattern(barcode)
                QMessageBox.information(
                    self,
                    tr("Fulfillment Updated", self.language),
                    tr("Barcode {barcode} has been removed from outsourced products. It will now be printed locally.", self.language).format(barcode=barcode),
                )
            else:
                ans = ask_yes_no(
                    self,
                    "Wildcard Rule Active",
                    "Barcode {barcode} is currently covered by wildcard rule '{rule}'.\nRemove the wildcard rule '{rule}'?",
                    self.language,
                    barcode=barcode,
                    rule=rule,
                )
                if ans and rule:
                    self.classifier.remove_pattern(rule)
        else:
            self.classifier.add_pattern(barcode)
            QMessageBox.information(
                self,
                tr("Fulfillment Updated", self.language),
                tr("Barcode {barcode} is now marked as OUTSOURCED. Orders will be saved as PDF and skipped during local printing.", self.language).format(barcode=barcode),
            )
        self.refresh()
        self.refresh_rules()

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
            self.refresh_rules()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                tr("Catalog delete failed", self.language),
                str(exc),
            )

    def export_csv(self) -> None:
        """Export the currently filtered catalog items to a CSV file."""
        products = self._filtered_products()
        if not products:
            QMessageBox.information(
                self,
                tr("Export CSV", self.language),
                tr("No products match the current filter to export.", self.language),
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export Catalog to CSV", self.language),
            "luma_catalog.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Barcode", "Display Name", "Stock Code", "Seller", "Category",
                    "Product Type", "Size Type", "Fulfillment", "Notes"
                ])
                for p in products:
                    is_out, _ = self.classifier.is_outsourced_barcode(p.barcode)
                    writer.writerow([
                        p.barcode, p.display_name, p.stock_code or "", p.seller or "",
                        p.category or "", p.product_type or "", p.size_type or "",
                        "Outsourced" if is_out else "In-House", p.notes or "",
                    ])
            QMessageBox.information(
                self,
                tr("Export Successful", self.language),
                tr("Exported {count} product(s) to:\n{path}", self.language).format(
                    count=len(products), path=file_path
                ),
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                tr("Export Failed", self.language),
                str(exc),
            )

    # -------------------------------------------------------------------------
    # Outsourced Rules Methods
    # -------------------------------------------------------------------------
    def refresh_rules(self, *_):
        patterns = self.classifier.patterns
        query = self.search_rules.text().strip().casefold()
        catalog_items = self.catalog.list_all()

        visible_patterns = [p for p in patterns if not query or query in p.casefold()]

        self.rules_table.setRowCount(0)
        report = self.classifier.load()
        redundant_map = dict(report.redundant_rules)

        for row_idx, pattern in enumerate(visible_patterns):
            is_wildcard = pattern.endswith("*")
            rule_type = tr("Wildcard Prefix", self.language) if is_wildcard else tr("Exact Barcode", self.language)

            # Count matches in master catalog
            matches = sum(
                1 for p in catalog_items
                if (fnmatch.fnmatchcase(p.barcode, pattern) if is_wildcard else p.barcode == pattern)
            )

            status = "Active"
            if pattern in redundant_map:
                status = f"Redundant (covered by {redundant_map[pattern]})"

            self.rules_table.insertRow(row_idx)
            self.rules_table.setItem(row_idx, 0, QTableWidgetItem(pattern))
            self.rules_table.setItem(row_idx, 1, QTableWidgetItem(rule_type))
            self.rules_table.setItem(row_idx, 2, QTableWidgetItem(f"{matches} " + tr("Products", self.language)))

            status_item = QTableWidgetItem(tr(status, self.language))
            if "Redundant" in status:
                status_item.setForeground(Qt.GlobalColor.yellow)
            else:
                status_item.setForeground(Qt.GlobalColor.green)
            self.rules_table.setItem(row_idx, 3, status_item)

            action_item = QTableWidgetItem("Double-click to remove")
            action_item.setForeground(Qt.GlobalColor.lightGray)
            self.rules_table.setItem(row_idx, 4, action_item)

        self.lbl_rules_summary.setText(
            tr("{visible} rules shown · {total} active forwarding rules", self.language).format(
                visible=len(visible_patterns),
                total=len(patterns),
            )
        )
        self.badge_rules_count.setText(f"{len(visible_patterns)} " + tr("Rules", self.language))
        self.btn_remove_rule.setEnabled(bool(visible_patterns))

    def add_outsourced_rule(self) -> None:
        raw = self.input_new_rule.text().strip()
        if not raw:
            return
        success = self.classifier.add_pattern(raw)
        if not success:
            QMessageBox.warning(
                self,
                tr("Duplicate Rule", self.language),
                tr("Rule '{rule}' is already present in the outsourced rules list.", self.language).format(rule=raw),
            )
            return

        self.input_new_rule.clear()
        self.refresh_rules()
        self.refresh()
        QMessageBox.information(
            self,
            tr("Rule Added", self.language),
            tr("Outsourced rule '{rule}' added successfully.", self.language).format(rule=raw),
        )

    def remove_selected_rule(self) -> None:
        rows = self.rules_table.selectionModel().selectedRows()
        if not rows:
            return
        pattern_item = self.rules_table.item(rows[0].row(), 0)
        if not pattern_item:
            return
        pattern = pattern_item.text()
        ans = ask_yes_no(
            self,
            "Remove Outsourced Rule",
            "Remove outsourced rule '{rule}'? Orders matching this rule will no longer be forwarded to suppliers.",
            self.language,
            rule=pattern,
        )
        if not ans:
            return
        self.classifier.remove_pattern(pattern)
        self.refresh_rules()
        self.refresh()

    def test_barcode_match(self) -> None:
        test_bc = self.input_test_barcode.text().strip()
        if not test_bc:
            self.lbl_test_result.setText("Enter a barcode above to test fulfillment routing.")
            self.lbl_test_result.setStyleSheet("color: #94a3b8; font-size: 8.5pt; font-style: italic;")
            return

        is_out, rule = self.classifier.is_outsourced_barcode(test_bc)
        if is_out:
            self.lbl_test_result.setText(
                f"✓ {tr('Matches rule', self.language)} '{rule}' → {tr('OUTSOURCED to external supplier (Skip local printing)', self.language)}"
            )
            self.lbl_test_result.setStyleSheet("color: #f59e0b; font-weight: 700; font-size: 9pt;")
        else:
            self.lbl_test_result.setText(
                f"ℹ {tr('No match', self.language)} → {tr('IN-HOUSE (Thermal printed locally)', self.language)}"
            )
            self.lbl_test_result.setStyleSheet("color: #14b8a6; font-weight: 700; font-size: 9pt;")

    def validate_rules(self) -> None:
        report = self.classifier.load(force=True)
        msg_parts = []
        if report.duplicates:
            msg_parts.append("Duplicates found:\n• " + "\n• ".join(report.duplicates))
        if report.redundant_rules:
            msg_parts.append(
                "Redundant rules found:\n• "
                + "\n• ".join(f"'{red}' is already covered by '{cov}'" for red, cov in report.redundant_rules)
            )
        if report.warnings:
            msg_parts.append("Warnings:\n• " + "\n• ".join(report.warnings))

        if not msg_parts:
            QMessageBox.information(
                self,
                tr("Rule Validation Report", self.language),
                tr(
                    "No validation issues found. All {count} rule(s) are valid and unique.",
                    self.language,
                ).format(count=len(report.valid_rules)),
            )
        else:
            QMessageBox.warning(
                self,
                tr("Rule Validation Report", self.language),
                "\n\n".join(msg_parts),
            )

    def open_outsourced_folder(self) -> None:
        folder = str(get_data_path("outsourced_labels"))
        os.makedirs(folder, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            QMessageBox.warning(self, tr("Open Folder", self.language), str(exc))

    def export_rules(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export Rules", self.language),
            "outsourced_products.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# Luma Outsourced Products Export\n")
                for pat in self.classifier.patterns:
                    f.write(f"{pat}\n")
            QMessageBox.information(
                self,
                tr("Export Successful", self.language),
                tr("Exported {count} rule(s) to:\n{path}", self.language).format(
                    count=len(self.classifier.patterns), path=file_path
                ),
            )
        except OSError as exc:
            QMessageBox.critical(self, tr("Export Failed", self.language), str(exc))

    def import_rules(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Import Rules", self.language),
            "",
            "Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return
        try:
            added = 0
            with open(file_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    token = line.split("#", 1)[0].strip()
                    if token and self.classifier.add_pattern(token):
                        added += 1
            self.refresh_rules()
            self.refresh()
            QMessageBox.information(
                self,
                tr("Import Successful", self.language),
                tr("Imported {count} new rule(s) from file.", self.language).format(count=added),
            )
        except OSError as exc:
            QMessageBox.critical(self, tr("Import Failed", self.language), str(exc))

    # Compatibility methods for older callers.
    def load_master_catalog(self, db_rows):
        self.catalog_table.setRowCount(0)
        for row_data in db_rows:
            row_idx = self.catalog_table.rowCount()
            self.catalog_table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data[:self.catalog_table.columnCount()]):
                self.catalog_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

    def apply_seller_overrides(self, overrides_dict):
        return
