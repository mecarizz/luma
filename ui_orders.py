"""Manual order lookup and carrier-specific label printing."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.manual_orders import prepare_package_for_cargo
from core.seller_models import CARGO_PROVIDERS, SellerProfile
from worker import SellerWorker


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

    def __init__(self, profiles: Iterable[SellerProfile]):
        super().__init__()
        self.profiles = list(profiles)

    def run(self) -> None:
        import trendyol_labels as labels

        packages: List[Dict[str, Any]] = []
        errors: List[str] = []
        for profile in self.profiles:
            if not profile.raw_api_key or not profile.raw_api_secret:
                errors.append(f"{profile.display_tag}: API credentials are missing.")
                continue
            try:
                found = labels.fetch_packages(
                    profile.statuses,
                    profile.lookback_hours / 24,
                    seller=_api_seller(profile),
                )
                packages.extend(found)
            except (Exception, SystemExit) as exc:
                errors.append(f"{profile.display_tag}: {type(exc).__name__}: {exc}")
        self.completed.emit((packages, errors))


class _PrintOrdersWorker(QThread):
    completed = Signal(object)

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
        import trendyol_labels as labels
        import trendyol_watcher as watcher

        prepared: Dict[str, List[Dict[str, Any]]] = {}
        errors: List[str] = []
        for package in self.packages:
            seller_id = str((package.get("_seller") or {}).get("id") or "")
            profile = self.profiles.get(seller_id)
            if profile is None:
                errors.append(f"Order {package.get('orderNumber', '?')}: seller profile is unavailable.")
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

        printed_count = 0
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
                errors.append(f"{profile.display_tag}: label generation/printing failed: {exc}")

        self.completed.emit((printed_count, errors))


class OrdersTab(QWidget):
    operation_started = Signal()
    operation_finished = Signal()

    def __init__(self, seller_manager=None):
        super().__init__()
        self.seller_manager = seller_manager
        self._profiles: List[SellerProfile] = []
        self._packages: List[Dict[str, Any]] = []
        self._worker: Optional[QThread] = None

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.seller_combo = QComboBox()
        self.fetch_button = QPushButton("Fetch Orders")
        controls.addWidget(QLabel("Seller:"))
        controls.addWidget(self.seller_combo, 1)
        controls.addWidget(self.fetch_button)
        layout.addLayout(controls)

        self.status_label = QLabel("Fetch orders to choose packages for label printing.")
        layout.addWidget(self.status_label)

        self.order_table = QTableWidget(0, 7)
        self.order_table.setHorizontalHeaderLabels(
            ["Select", "Seller", "Order No.", "Package ID", "Customer", "Current Cargo", "Status"]
        )
        self.order_table.setSortingEnabled(False)
        self.order_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.order_table.itemChanged.connect(self._update_enabled)
        layout.addWidget(self.order_table)

        actions = QHBoxLayout()
        self.print_tex_button = QPushButton("Print as TEX")
        self.print_dhl_button = QPushButton("Print as DHL")
        self.custom_cargo_combo = QComboBox()
        self.custom_cargo_combo.addItem("Select custom cargo...", None)
        for code, name in CARGO_PROVIDERS.items():
            self.custom_cargo_combo.addItem(name, code)
        self.custom_cargo_button = QPushButton("Print as selected cargo")
        actions.addWidget(self.print_tex_button)
        actions.addWidget(self.print_dhl_button)
        actions.addWidget(self.custom_cargo_combo)
        actions.addWidget(self.custom_cargo_button)
        layout.addLayout(actions)

        self.fetch_button.clicked.connect(self.fetch_orders)
        self.print_tex_button.clicked.connect(lambda: self.print_selected("TEX"))
        self.print_dhl_button.clicked.connect(lambda: self.print_selected("DHLECOMMP"))
        self.custom_cargo_button.clicked.connect(self.print_custom_selection)
        self.custom_cargo_combo.currentIndexChanged.connect(self._update_enabled)
        self._update_enabled()

    def set_manager(self, seller_manager) -> None:
        self.seller_manager = seller_manager
        self.refresh_sellers()

    def refresh_sellers(self) -> None:
        selected = self.seller_combo.currentData()
        self._profiles = self.seller_manager.list_all() if self.seller_manager else []
        self.seller_combo.clear()
        self.seller_combo.addItem("All sellers", None)
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
        has_selection = bool(self._selected_packages())
        self.print_tex_button.setEnabled(not busy and has_selection)
        self.print_dhl_button.setEnabled(not busy and has_selection)
        self.custom_cargo_button.setEnabled(
            not busy and has_selection and self.custom_cargo_combo.currentData() is not None
        )

    def _selected_packages(self) -> List[Dict[str, Any]]:
        selected = []
        for row, package in enumerate(self._packages):
            item = self.order_table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                selected.append(package)
        return selected

    def fetch_orders(self) -> None:
        profiles = self._selected_profiles()
        if not profiles:
            QMessageBox.information(self, "Fetch orders", "No seller profiles are configured.")
            return
        self.status_label.setText("Fetching packages using each seller's configured statuses and lookback...")
        worker = _FetchOrdersWorker(profiles)
        worker.completed.connect(self._on_orders_fetched)
        self._start_worker(worker)

    def _on_orders_fetched(self, result: Tuple[List[Dict[str, Any]], List[str]]) -> None:
        self._packages, errors = result
        self.order_table.setRowCount(0)
        for package in self._packages:
            seller = package.get("_seller") or {}
            address = package.get("shipmentAddress") or {}
            values = (
                "",
                str(seller.get("name") or seller.get("id") or ""),
                str(package.get("orderNumber") or ""),
                str(package.get("shipmentPackageId") or ""),
                str(address.get("fullName") or ""),
                str(package.get("cargoProviderName") or package.get("cargoProviderCode") or "Unknown"),
                str(package.get("status") or ""),
            )
            row = self.order_table.rowCount()
            self.order_table.insertRow(row)
            checkbox = QTableWidgetItem()
            checkbox.setFlags((checkbox.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            checkbox.setCheckState(Qt.Unchecked)
            self.order_table.setItem(row, 0, checkbox)
            for column, value in enumerate(values[1:], 1):
                self.order_table.setItem(row, column, QTableWidgetItem(value))

        summary = f"Found {len(self._packages)} package(s). Select the orders to print."
        if errors:
            summary += f" {len(errors)} seller request(s) failed."
        self.status_label.setText(summary)
        if errors:
            QMessageBox.warning(self, "Some orders could not be fetched", "\n".join(errors))
        self._update_enabled()

    def print_custom_selection(self) -> None:
        target = self.custom_cargo_combo.currentData()
        if target:
            self.print_selected(str(target))

    def print_selected(self, target_cargo: str) -> None:
        packages = self._selected_packages()
        if not packages:
            QMessageBox.information(self, "Print labels", "Select at least one package first.")
            return
        label = CARGO_PROVIDERS.get(target_cargo, target_cargo)
        answer = QMessageBox.question(
            self,
            "Change cargo and print labels",
            f"Switch the selected package(s) to {label} in Trendyol and print their refreshed labels?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self.status_label.setText(f"Preparing and printing {len(packages)} package(s) as {label}...")
        worker = _PrintOrdersWorker(packages, self._profiles, target_cargo)
        worker.completed.connect(self._on_labels_printed)
        self._start_worker(worker)

    def _on_labels_printed(self, result: Tuple[int, List[str]]) -> None:
        printed_count, errors = result
        message = f"Printed {printed_count} label(s)."
        if errors:
            message += "\n\n" + "\n".join(errors)
        self.status_label.setText(
            f"Printed {printed_count} label(s)." if not errors else "Printing finished with errors."
        )
        if errors:
            QMessageBox.warning(self, "Label printing results", message)
        else:
            QMessageBox.information(self, "Label printing complete", message)

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
