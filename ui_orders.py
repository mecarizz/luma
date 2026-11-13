"""Manual order lookup, filtering, and carrier-specific label printing."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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

from core.classifier import ClassificationResult, OutsourcedClassifier
from core.i18n import ask_yes_no, tr
from core.logger import CallbackLogHandler, get_logger
from core.manual_orders import prepare_package_for_cargo
from core.paths import get_data_path
from core.reporting import ReportingEngine
from core.seller_models import CARGO_PROVIDERS, SellerProfile
from ui_components import SearchInput, SectionHeader, StatusBadge
from worker import SellerWorker


class OutsourcedOrderNotificationDialog(QDialog):
    """Modern modal dialog alerting user to orders containing outsourced products."""

    ACTION_SAVE_PDF = 1
    ACTION_REVIEW = 2
    ACTION_PRINT_ANYWAY = 3
    ACTION_CANCEL = 0

    def __init__(
        self,
        parent: Optional[QWidget],
        outsourced_items: List[Tuple[Dict[str, Any], ClassificationResult]],
        target_cargo: str,
        language: str = "en",
    ):
        super().__init__(parent)
        self.outsourced_items = outsourced_items
        self.target_cargo = target_cargo
        self.language = language
        self.selected_action = self.ACTION_CANCEL

        self.setWindowTitle(tr("Outsourced Order Notification", language))
        self.setMinimumWidth(680)
        self.setStyleSheet("background-color: #111827; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)

        # Alert Banner
        banner = QFrame()
        banner.setObjectName("panel")
        banner.setStyleSheet(
            "QFrame#panel { background-color: #1a2217; border: 1px solid #eab308; border-radius: 10px; }"
        )
        b_layout = QHBoxLayout(banner)
        b_layout.setContentsMargins(16, 14, 16, 14)
        b_layout.setSpacing(14)

        icon_lbl = QLabel("📦")
        icon_lbl.setStyleSheet("font-size: 22pt;")
        b_layout.addWidget(icon_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        title_lbl = QLabel(tr("Outsourced Order Notification", language))
        title_lbl.setStyleSheet("color: #facc15; font-weight: 700; font-size: 11pt;")

        msg_lbl = QLabel(
            tr(
                "This order contains outsourced products and will not be printed locally because another company sends them out for us.\n\n"
                "Would you like to save it as PDF on your computer or review it?",
                language,
            )
        )
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("color: #e2e8f0; font-size: 9.5pt;")

        text_layout.addWidget(title_lbl)
        text_layout.addWidget(msg_lbl)
        b_layout.addLayout(text_layout, 1)
        layout.addWidget(banner)

        # Table showing affected outsourced orders
        lbl_table_header = QLabel(f"<b>{tr('Affected Outsourced Order(s):', language)}</b> ({len(outsourced_items)})")
        lbl_table_header.setStyleSheet("color: #cbd5e1; font-size: 9.5pt;")
        layout.addWidget(lbl_table_header)

        table = QTableWidget(len(outsourced_items), 4)
        table.setHorizontalHeaderLabels([
            tr("Order No.", language),
            tr("Customer", language),
            tr("Outsourced Barcode(s)", language),
            tr("Matched Rule", language),
        ])
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        for row, (pkg, res) in enumerate(outsourced_items):
            order_no = str(pkg.get("orderNumber") or pkg.get("shipmentPackageId") or "")
            cust = str((pkg.get("shipmentAddress") or {}).get("fullName") or "—")
            matched_bcs = ", ".join(str(ln.get("barcode") or "") for ln in res.matched_lines)
            matched_rules = ", ".join(sorted(res.matched_rules)) if res.matched_rules else "outsourced"

            table.setItem(row, 0, QTableWidgetItem(order_no))
            table.setItem(row, 1, QTableWidgetItem(cust))
            table.setItem(row, 2, QTableWidgetItem(matched_bcs))
            table.setItem(row, 3, QTableWidgetItem(matched_rules))

        table.setMaximumHeight(160)
        layout.addWidget(table)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_save_pdf = QPushButton(tr("Save as PDF", language))
        self.btn_save_pdf.setObjectName("primaryButton")
        self.btn_save_pdf.setStyleSheet(
            "background-color: #059669; border-color: #10b981; color: #ffffff; font-weight: 700;"
        )
        self.btn_save_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_save_pdf.clicked.connect(self._on_save_pdf)

        self.btn_review = QPushButton(tr("Review Orders", language))
        self.btn_review.setObjectName("ghostButton")
        self.btn_review.setCursor(Qt.PointingHandCursor)
        self.btn_review.clicked.connect(self._on_review)

        self.btn_print_anyway = QPushButton(tr("Print Anyway", language))
        self.btn_print_anyway.setObjectName("destructiveButton")
        self.btn_print_anyway.setStyleSheet(
            "background-color: #78350f; border-color: #d97706; color: #fef3c7;"
        )
        self.btn_print_anyway.setCursor(Qt.PointingHandCursor)
        self.btn_print_anyway.clicked.connect(self._on_print_anyway)

        self.btn_cancel = QPushButton(tr("Cancel", language))
        self.btn_cancel.setObjectName("ghostButton")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel)

        btn_layout.addWidget(self.btn_save_pdf)
        btn_layout.addWidget(self.btn_review)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_print_anyway)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _on_save_pdf(self) -> None:
        self.selected_action = self.ACTION_SAVE_PDF
        self.accept()

    def _on_review(self) -> None:
        self.selected_action = self.ACTION_REVIEW
        self.accept()

    def _on_print_anyway(self) -> None:
        self.selected_action = self.ACTION_PRINT_ANYWAY
        self.accept()

    def _on_cancel(self) -> None:
        self.selected_action = self.ACTION_CANCEL
        self.reject()


def _api_seller(profile: SellerProfile) -> Dict[str, str]:
    return {
        "id": profile.seller_id,
        "key": profile.raw_api_key,
        "secret": profile.raw_api_secret,
        "name": profile.name,
        "cargo": profile.preferred_cargo,
    }


class _FetchOrdersWorker(QThread):
    completed = Signal(object)
    log_emitted = Signal(str)

    def __init__(self, profiles: Iterable[SellerProfile]):
        super().__init__()
        self.profiles = list(profiles)

    def run(self) -> None:
        packages: List[Dict[str, Any]] = []
        errors: List[str] = []
        logger = get_logger()
        log_handler = CallbackLogHandler(self.log_emitted.emit)
        log_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(log_handler)
        try:
            import trendyol_labels as labels

            for profile in self.profiles:
                credential_error = profile.credential_error
                if credential_error:
                    error = f"{profile.display_tag}: {credential_error}"
                    errors.append(error)
                    logger.error("Manual order fetch blocked: %s", error)
                    continue
                try:
                    logger.info(
                        "[%s] Manual order fetch started: statuses=%s lookback_hours=%s",
                        profile.display_tag,
                        ",".join(profile.statuses),
                        profile.lookback_hours,
                    )
                    found = labels.fetch_packages(
                        profile.statuses,
                        profile.lookback_hours / 24,
                        seller=_api_seller(profile),
                    )
                    packages.extend(found)
                    logger.info(
                        "[%s] Manual order fetch completed: packages=%d",
                        profile.display_tag,
                        len(found),
                    )
                except (Exception, SystemExit) as exc:
                    error = f"{profile.display_tag}: {type(exc).__name__}: {exc}"
                    errors.append(error)
                    logger.error("[%s] Manual order fetch failed: %s", profile.display_tag, exc)
        except (Exception, SystemExit) as exc:
            error = f"Order fetch could not start: {type(exc).__name__}: {exc}"
            errors.append(error)
            logger.error("Manual order fetch worker failed to initialize: %s", exc)
        finally:
            logger.removeHandler(log_handler)
            self.completed.emit((packages, errors))


class _PrintOrdersWorker(QThread):
    completed = Signal(object)
    log_emitted = Signal(str)

    def __init__(
        self,
        packages: Iterable[Dict[str, Any]],
        profiles: Iterable[SellerProfile],
        target_cargo: str,
    ):
        super().__init__()
        self.packages = list(packages)
        self.profiles = {profile.seller_id: profile for profile in profiles}
        self.target_cargo = target_cargo

    def run(self) -> None:
        logger = get_logger()
        printed_count = 0
        errors: List[str] = []
        log_handler = CallbackLogHandler(self.log_emitted.emit)
        log_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(log_handler)
        try:
            import trendyol_labels as labels
            import trendyol_watcher as watcher

            prepared: Dict[str, List[Dict[str, Any]]] = {}
            for package in self.packages:
                seller_id = str((package.get("_seller") or {}).get("id") or "")
                profile = self.profiles.get(seller_id)
                if profile is None:
                    errors.append(
                        f"Order {package.get('orderNumber', '?')}: seller profile is unavailable."
                    )
                    continue

                try:
                    seller = _api_seller(profile)
                    options = SellerWorker._watcher_options(profile)
                    refreshed = prepare_package_for_cargo(
                        package,
                        seller,
                        options,
                        self.target_cargo,
                    )
                    prepared.setdefault(seller_id, []).append(refreshed)
                except (Exception, SystemExit) as exc:
                    errors.append(f"Order {package.get('orderNumber', '?')}: {exc}")

            for seller_id, seller_packages in prepared.items():
                profile = self.profiles[seller_id]
                try:
                    labels.register_font()
                    pdf_path = watcher.make_label_pdf(
                        seller_packages,
                        SellerWorker._watcher_options(profile),
                    )
                    if watcher.send_to_printer(pdf_path, profile.printer_name):
                        printed_count += len(seller_packages)
                    else:
                        errors.append(
                            f"{profile.display_tag}: could not send {len(seller_packages)} label(s) "
                            f"to printer {profile.printer_name!r}. PDF: {pdf_path}"
                        )
                except (Exception, SystemExit) as exc:
                    errors.append(
                        f"{profile.display_tag}: label generation/printing failed: {exc}"
                    )
        except (Exception, SystemExit) as exc:
            errors.append(f"Label printing could not start: {type(exc).__name__}: {exc}")
            logger.error("Manual label printing worker failed to initialize: %s", exc)
        finally:
            logger.info(
                "Manual label printing completed: printed=%d errors=%d",
                printed_count,
                len(errors),
            )
            logger.removeHandler(log_handler)
            self.completed.emit((printed_count, errors))


class OrdersTab(QWidget):
    operation_started = Signal()
    operation_finished = Signal()
    log_emitted = Signal(str)

    def __init__(self, seller_manager=None):
        super().__init__()
        self.seller_manager = seller_manager
        self._profiles: List[SellerProfile] = []
        self._packages: List[Dict[str, Any]] = []
        self._worker: Optional[QThread] = None
        self.language = "en"
        self._status_template = "Fetch orders to choose packages for label printing."
        self._status_values: Dict[str, Any] = {}
        self._classifier = OutsourcedClassifier(str(get_data_path("outsourced_products.txt")))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # Header with actions
        self.header = SectionHeader(
            title="Orders & Thermal Labels",
            subtitle="Manual package retrieval, carrier reassignment, and thermal printing.",
        )
        layout.addWidget(self.header)

        # Controls Toolbar Card
        controls_card = QFrame()
        controls_card.setObjectName("panel")
        controls_layout = QHBoxLayout(controls_card)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(12)

        self.seller_label = QLabel("Seller:")
        self.seller_label.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        self.seller_combo = QComboBox()
        self.seller_combo.setMinimumWidth(180)

        self.fetch_button = QPushButton("Fetch Orders")
        self.fetch_button.setObjectName("primaryButton")
        self.fetch_button.setCursor(Qt.PointingHandCursor)

        self.search_input = SearchInput(placeholder="Filter by order no, package ID, customer...", debounce_ms=150)
        self.search_input.debounced_text_changed.connect(self._apply_filter)

        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setObjectName("ghostButton")
        self.btn_select_all.setCursor(Qt.PointingHandCursor)
        self.btn_select_all.clicked.connect(self._select_all)

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.setObjectName("ghostButton")
        self.btn_deselect_all.setCursor(Qt.PointingHandCursor)
        self.btn_deselect_all.clicked.connect(self._deselect_all)

        controls_layout.addWidget(self.seller_label)
        controls_layout.addWidget(self.seller_combo)
        controls_layout.addWidget(self.fetch_button)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(self.search_input, 1)
        controls_layout.addWidget(self.btn_select_all)
        controls_layout.addWidget(self.btn_deselect_all)

        layout.addWidget(controls_card)

        # Status & Selection indicator row
        status_row = QHBoxLayout()
        self.status_label = QLabel("Fetch orders to choose packages for label printing.")
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")

        self.badge_selection = StatusBadge("Selected: 0", "neutral")

        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.badge_selection)
        layout.addLayout(status_row)

        # Orders Table — 8 columns including Fulfillment routing indicator
        self.order_table = QTableWidget(0, 8)
        self.order_table.setHorizontalHeaderLabels([
            "Select", "Seller", "Order No.", "Package ID", "Customer", "City", "Current Cargo", "Fulfillment"
        ])
        self.order_table.setSortingEnabled(False)
        self.order_table.setAlternatingRowColors(True)
        self.order_table.verticalHeader().setVisible(False)
        self.order_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.order_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.order_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.order_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.order_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.order_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.order_table.itemChanged.connect(self._update_enabled)
        layout.addWidget(self.order_table, 1)

        # Actions Bottom Card
        actions_card = QFrame()
        actions_card.setObjectName("panel")
        actions_layout = QHBoxLayout(actions_card)
        actions_layout.setContentsMargins(14, 12, 14, 12)
        actions_layout.setSpacing(12)

        self.print_tex_button = QPushButton("Print as TEX")
        self.print_tex_button.setObjectName("primaryButton")
        self.print_tex_button.setCursor(Qt.PointingHandCursor)

        self.print_dhl_button = QPushButton("Print as DHL")
        self.print_dhl_button.setObjectName("primaryButton")
        self.print_dhl_button.setCursor(Qt.PointingHandCursor)

        self.custom_cargo_combo = QComboBox()
        self.custom_cargo_combo.addItem("Select custom cargo...", None)
        for code, name in CARGO_PROVIDERS.items():
            self.custom_cargo_combo.addItem(name, code)

        self.custom_cargo_button = QPushButton("Print as selected cargo")
        self.custom_cargo_button.setCursor(Qt.PointingHandCursor)

        actions_layout.addWidget(self.print_tex_button)
        actions_layout.addWidget(self.print_dhl_button)
        actions_layout.addSpacing(16)
        actions_layout.addWidget(self.custom_cargo_combo)
        actions_layout.addWidget(self.custom_cargo_button)
        actions_layout.addStretch()

        layout.addWidget(actions_card)

        # Signals
        self.fetch_button.clicked.connect(self.fetch_orders)
        self.print_tex_button.clicked.connect(lambda: self.print_selected("TEX"))
        self.print_dhl_button.clicked.connect(lambda: self.print_selected("DHLECOMMP"))
        self.custom_cargo_button.clicked.connect(self.print_custom_selection)
        self.custom_cargo_combo.currentIndexChanged.connect(self._update_enabled)

        self.set_language("en")
        self._update_enabled()

    def set_language(self, language: str) -> None:
        self.language = language
        self.header.set_language(language)
        selected_seller = self.seller_combo.currentData()
        self.seller_combo.clear()
        self.seller_combo.addItem(tr("All sellers", language), None)
        for profile in self._profiles:
            self.seller_combo.addItem(
                f"{profile.display_tag} ({profile.seller_id})",
                profile.seller_id,
            )
        index = self.seller_combo.findData(selected_seller)
        if index >= 0:
            self.seller_combo.setCurrentIndex(index)

        self.fetch_button.setText(tr("Fetch Orders", language))
        self.seller_label.setText(tr("Seller:", language))
        self.status_label.setText(tr(self._status_template, language).format(**self._status_values))
        self.search_input.setPlaceholderText(tr("Filter by order no, package ID, customer...", language))
        self.btn_select_all.setText(tr("Select All", language))
        self.btn_deselect_all.setText(tr("Deselect All", language))

        self.order_table.setHorizontalHeaderLabels([
            tr("Select", language),
            tr("Seller", language),
            tr("Order No.", language),
            tr("Package ID", language),
            tr("Customer", language),
            tr("City", language),
            tr("Current Cargo", language),
            tr("Fulfillment", language),
        ])
        for row, package in enumerate(self._packages):
            cargo_item = self.order_table.item(row, 6)
            fulf_item = self.order_table.item(row, 7)
            if cargo_item is not None:
                cargo = str(
                    package.get("cargoProviderName")
                    or package.get("cargoProviderCode")
                    or "Unknown"
                )
                cargo_item.setText(tr(cargo, language))
            if fulf_item is not None:
                raw_fulf = fulf_item.data(Qt.UserRole) or ""
                fulf_item.setText(tr(raw_fulf, language))

        self.print_tex_button.setText(tr("Print as TEX", language))
        self.print_dhl_button.setText(tr("Print as DHL", language))

        target = self.custom_cargo_combo.currentData()
        self.custom_cargo_combo.clear()
        self.custom_cargo_combo.addItem(tr("Select custom cargo...", language), None)
        for code, name in CARGO_PROVIDERS.items():
            self.custom_cargo_combo.addItem(tr(name, language), code)
        cargo_index = self.custom_cargo_combo.findData(target)
        if cargo_index >= 0:
            self.custom_cargo_combo.setCurrentIndex(cargo_index)
        self.custom_cargo_button.setText(tr("Print as selected cargo", language))
        self._update_enabled()

    def _set_status(self, template: str, **values: Any) -> None:
        self._status_template = template
        self._status_values = values
        self.status_label.setText(tr(template, self.language).format(**values))

    def set_manager(self, seller_manager) -> None:
        self.seller_manager = seller_manager
        self.refresh_sellers()

    def refresh_sellers(self) -> None:
        selected = self.seller_combo.currentData()
        self._profiles = self.seller_manager.list_all() if self.seller_manager else []
        self.seller_combo.clear()
        self.seller_combo.addItem(tr("All sellers", self.language), None)
        for profile in self._profiles:
            self.seller_combo.addItem(f"{profile.display_tag} ({profile.seller_id})", profile.seller_id)
        index = self.seller_combo.findData(selected)
        if index >= 0:
            self.seller_combo.setCurrentIndex(index)
        self._update_enabled()

    def _selected_profiles(self) -> List[SellerProfile]:
        seller_id = self.seller_combo.currentData()
        if seller_id is None:
            return list(self._profiles)
        return [profile for profile in self._profiles if profile.seller_id == seller_id]

    def _update_enabled(self, *_args) -> None:
        busy = self._worker is not None
        has_profiles = bool(self._profiles)
        self.fetch_button.setEnabled(not busy and has_profiles)
        selected_packages = self._selected_packages()
        has_selection = bool(selected_packages)
        self.print_tex_button.setEnabled(not busy and has_selection)
        self.print_dhl_button.setEnabled(not busy and has_selection)
        self.custom_cargo_button.setEnabled(
            not busy and has_selection and self.custom_cargo_combo.currentData() is not None
        )
        self.btn_select_all.setEnabled(not busy and bool(self._packages))
        self.btn_deselect_all.setEnabled(not busy and bool(self._packages))

        count = len(selected_packages)
        self.badge_selection.setText(f"{tr('Selected', self.language)}: {count}")
        if count > 0:
            self.badge_selection.set_variant("info")
        else:
            self.badge_selection.set_variant("neutral")

    def _selected_packages(self) -> List[Dict[str, Any]]:
        selected = []
        for row, package in enumerate(self._packages):
            if row < self.order_table.rowCount():
                item = self.order_table.item(row, 0)
                if item is not None and item.checkState() == Qt.Checked:
                    selected.append(package)
        return selected

    def _select_all(self) -> None:
        self.order_table.blockSignals(True)
        for row in range(self.order_table.rowCount()):
            if not self.order_table.isRowHidden(row):
                item = self.order_table.item(row, 0)
                if item:
                    item.setCheckState(Qt.Checked)
        self.order_table.blockSignals(False)
        self._update_enabled()

    def _deselect_all(self) -> None:
        self.order_table.blockSignals(True)
        for row in range(self.order_table.rowCount()):
            item = self.order_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self.order_table.blockSignals(False)
        self._update_enabled()

    def _apply_filter(self, query: str) -> None:
        query_norm = query.strip().casefold()
        for row in range(self.order_table.rowCount()):
            if not query_norm:
                self.order_table.setRowHidden(row, False)
                continue
            row_text = " ".join(
                self.order_table.item(row, col).text()
                for col in range(1, self.order_table.columnCount())
                if self.order_table.item(row, col)
            ).casefold()
            self.order_table.setRowHidden(row, query_norm not in row_text)

    def fetch_orders(self) -> None:
        profiles = self._selected_profiles()
        if not profiles:
            QMessageBox.information(
                self,
                tr("Fetch orders", self.language),
                tr("No seller profiles are configured.", self.language),
            )
            return
        self._set_status("Fetching packages using each seller's configured statuses and lookback...")
        worker = _FetchOrdersWorker(profiles)
        worker.completed.connect(self._on_orders_fetched)
        worker.log_emitted.connect(self.log_emitted)
        self._start_worker(worker)

    def _on_orders_fetched(self, result: Tuple[List[Dict[str, Any]], List[str]]) -> None:
        self._packages, errors = result
        self._classifier.load(force=True)  # Reload rules in case they changed

        # Build a seller_id → display_tag lookup from loaded profiles
        profile_by_id: Dict[str, SellerProfile] = {p.seller_id: p for p in self._profiles}

        self.order_table.setRowCount(0)
        outsourced_in_batch = 0

        for package in self._packages:
            seller = package.get("_seller") or {}
            address = package.get("shipmentAddress") or {}

            # Resolve seller display name: prefer profile name over API-returned name/id
            seller_id_str = str(seller.get("id") or "")
            profile = profile_by_id.get(seller_id_str)
            if profile and profile.name:
                seller_display = profile.display_tag  # Custom name set by user
            elif seller.get("name"):
                seller_display = str(seller["name"])
            elif seller_id_str:
                seller_display = f"Seller {seller_id_str}"
            else:
                seller_display = "—"

            # Customer info
            full_name = str(address.get("fullName") or "—")
            city = str(address.get("city") or address.get("district") or "")
            phone = str(address.get("fullAddress") or "")

            # Outsourced routing check
            classification = self._classifier.route_package(package)
            if classification.kind == "normal":
                fulf_text = "In-House"
                fulf_color = "#14b8a6"
            elif classification.kind == "outsourced":
                fulf_text = "Outsourced"
                fulf_color = "#f59e0b"
                outsourced_in_batch += 1
            else:
                fulf_text = "Mixed"
                fulf_color = "#f97316"
                outsourced_in_batch += 1

            cargo_str = tr(
                str(package.get("cargoProviderName") or package.get("cargoProviderCode") or "Unknown"),
                self.language,
            )
            status_str = tr(str(package.get("status") or ""), self.language)

            row = self.order_table.rowCount()
            self.order_table.insertRow(row)

            # Col 0: Checkbox
            checkbox = QTableWidgetItem()
            checkbox.setFlags((checkbox.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            checkbox.setCheckState(Qt.Unchecked)
            self.order_table.setItem(row, 0, checkbox)

            # Col 1: Seller display name
            seller_item = QTableWidgetItem(seller_display)
            seller_item.setToolTip(f"Seller ID: {seller_id_str}")
            self.order_table.setItem(row, 1, seller_item)

            # Col 2: Order No.
            self.order_table.setItem(row, 2, QTableWidgetItem(str(package.get("orderNumber") or "")))

            # Col 3: Package ID
            self.order_table.setItem(row, 3, QTableWidgetItem(str(package.get("shipmentPackageId") or "")))

            # Col 4: Customer full name (with tooltip showing address)
            cust_item = QTableWidgetItem(full_name)
            cust_item.setToolTip(phone or full_name)
            self.order_table.setItem(row, 4, cust_item)

            # Col 5: City
            self.order_table.setItem(row, 5, QTableWidgetItem(city))

            # Col 6: Cargo
            self.order_table.setItem(row, 6, QTableWidgetItem(cargo_str))

            # Col 7: Fulfillment indicator
            fulf_item = QTableWidgetItem(tr(fulf_text, self.language))
            fulf_item.setData(Qt.UserRole, fulf_text)
            fulf_item.setTextAlignment(Qt.AlignCenter)
            # Tint the fulfillment cell to draw attention
            self.order_table.setItem(row, 7, fulf_item)

        failed_text = ""
        if errors:
            failed_text = " " + tr(
                "{count} seller request(s) failed.",
                self.language,
            ).format(count=len(errors))

        outsourced_note = ""
        if outsourced_in_batch:
            outsourced_note = " ⚠ " + tr(
                "{count} outsourced/mixed order(s) detected.",
                self.language,
            ).format(count=outsourced_in_batch)

        self._set_status(
            "Found {count} package(s). Select the orders to print.{failed_text}{outsourced_note}",
            count=len(self._packages),
            failed_text=failed_text,
            outsourced_note=outsourced_note,
        )
        if errors:
            QMessageBox.warning(
                self,
                tr("Some orders could not be fetched", self.language),
                "\n".join(errors),
            )
        self._apply_filter(self.search_input.text())
        self._update_enabled()

    def print_custom_selection(self) -> None:
        target = self.custom_cargo_combo.currentData()
        if target:
            self.print_selected(str(target))

    def print_selected(self, target_cargo: str) -> None:
        packages = self._selected_packages()
        if not packages:
            QMessageBox.information(
                self,
                tr("Print labels", self.language),
                tr("Select at least one package first.", self.language),
            )
            return

        # --- Outsourced routing check ---
        self._classifier.load()
        outsourced_items: List[Tuple[Dict[str, Any], ClassificationResult]] = []
        normal_packages: List[Dict[str, Any]] = []

        for pkg in packages:
            classification = self._classifier.route_package(pkg)
            if classification.kind in ("outsourced", "mixed"):
                outsourced_items.append((pkg, classification))
            if classification.kind == "normal":
                normal_packages.append(pkg)

        if outsourced_items:
            dlg = OutsourcedOrderNotificationDialog(
                self, outsourced_items, target_cargo, language=self.language
            )
            dlg.exec()

            if dlg.selected_action == OutsourcedOrderNotificationDialog.ACTION_CANCEL:
                return
            elif dlg.selected_action == OutsourcedOrderNotificationDialog.ACTION_SAVE_PDF:
                # Save outsourced PDFs and only print normal packages
                saved_count = self._save_outsourced_pdfs(outsourced_items, target_cargo)
                if saved_count > 0:
                    QMessageBox.information(
                        self,
                        tr("Outsourced PDFs Saved", self.language),
                        tr(
                            "Saved {count} outsourced order PDF(s) to your outsourced labels folder.",
                            self.language,
                        ).format(count=saved_count),
                    )
                # Also include the in-house portions of mixed orders
                for pkg, res in outsourced_items:
                    if res.kind == "mixed" and res.unmatched_lines:
                        normal_packages.append(pkg)
                if not normal_packages:
                    return
                # Proceed with just in-house packages
                packages = normal_packages
            elif dlg.selected_action == OutsourcedOrderNotificationDialog.ACTION_REVIEW:
                # Navigate to dashboard outsourced dialog — just open outsourced folder
                folder = str(get_data_path("outsourced_labels"))
                os.makedirs(folder, exist_ok=True)
                try:
                    if sys.platform.startswith("win"):
                        os.startfile(folder)
                    else:
                        subprocess.Popen(["xdg-open", folder])
                except Exception:
                    pass
                return
            elif dlg.selected_action == OutsourcedOrderNotificationDialog.ACTION_PRINT_ANYWAY:
                # User explicitly wants everything printed — proceed with all packages
                pass

        label = CARGO_PROVIDERS.get(target_cargo, target_cargo)
        answer = ask_yes_no(
            self,
            "Change cargo and print labels",
            "Switch the selected package(s) to {cargo} in Trendyol and print their refreshed labels?",
            self.language,
            cargo=label,
        )
        if not answer:
            return

        self._set_status(
            "Preparing and printing {count} package(s) as {cargo}...",
            count=len(packages),
            cargo=label,
        )
        worker = _PrintOrdersWorker(packages, self._profiles, target_cargo)
        worker.completed.connect(self._on_labels_printed)
        worker.log_emitted.connect(self.log_emitted)
        self._start_worker(worker)

    def _save_outsourced_pdfs(
        self,
        items: List[Tuple[Dict[str, Any], ClassificationResult]],
        target_cargo: str,
    ) -> int:
        """Save outsourced order PDFs using trendyol_labels; returns number saved."""
        saved = 0
        profile_by_id: Dict[str, SellerProfile] = {p.seller_id: p for p in self._profiles}
        try:
            import trendyol_labels as labels
            labels.register_font()
            for pkg, res in items:
                seller_id_str = str((pkg.get("_seller") or {}).get("id") or "")
                profile = profile_by_id.get(seller_id_str)
                if profile is None:
                    continue
                try:
                    opts = SellerWorker._watcher_options(profile)
                    path = labels.save_outsourced_pdf(pkg, opts.label, kind=res.kind)
                    if path:
                        saved += 1
                except Exception as exc:
                    get_logger().warning("Could not save outsourced PDF for order %s: %s", pkg.get("orderNumber"), exc)
        except Exception as exc:
            get_logger().error("Outsourced PDF save failed: %s", exc)
        return saved

    def _on_labels_printed(self, result: Tuple[int, List[str]]) -> None:
        printed_count, errors = result
        message = tr("Printed {count} label(s).", self.language).format(count=printed_count)
        if errors:
            message += "\n\n" + "\n".join(errors)
        self._set_status(
            "Printed {count} label(s)." if not errors else "Printing finished with errors.",
            count=printed_count,
        )
        if errors:
            QMessageBox.warning(self, tr("Label printing results", self.language), message)
        else:
            QMessageBox.information(self, tr("Label printing complete", self.language), message)

    def _start_worker(self, worker: QThread) -> None:
        self._worker = worker
        worker.finished.connect(self._on_worker_finished)
        self.operation_started.emit()
        self._update_enabled()
        worker.start()

    def _on_worker_finished(self) -> None:
        self._worker = None
        self.operation_finished.emit()
        self._update_enabled()

    def stop_worker(self) -> bool:
        if self._worker is not None and self._worker.isRunning():
            return self._worker.wait(10_000)
        return True
