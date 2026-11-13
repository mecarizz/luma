"""Seller management and Trendyol API configuration UI."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.i18n import ask_yes_no, tr
from core.security import mask_secret_for_ui
from core.seller_manager import SellerManager
from core.seller_models import CARGO_PROVIDERS, SellerProfile
from ui_components import SectionHeader, StatusBadge


class SellersTab(QWidget):
    seller_configuration_changed = Signal()

    def __init__(self, seller_manager: Optional[SellerManager] = None):
        super().__init__()
        self.seller_manager = seller_manager
        self.language = "en"
        self._selected_seller_id: Optional[str] = None
        self._seller_status: dict[str, str] = {}

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(14)

        # Header
        self.header = SectionHeader(
            title="Seller Accounts & API Configuration",
            subtitle="Manage store connections, encrypted API credentials, cargo routing, and thermal printers.",
        )
        root_layout.addWidget(self.header)

        # Main Split Content
        body_layout = QHBoxLayout()
        body_layout.setSpacing(16)

        # ---------------- Left Panel: Seller List Card ----------------
        left_card = QFrame()
        left_card.setObjectName("panel")
        left_card.setFixedWidth(280)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        self.lbl_stores_title = QLabel("Connected Stores")
        self.lbl_stores_title.setObjectName("sectionTitle")
        left_layout.addWidget(self.lbl_stores_title)

        self.seller_list = QListWidget()
        self.seller_list.setStyleSheet(
            "QListWidget::item { padding: 8px 10px; border-radius: 6px; margin-bottom: 3px; } "
            "QListWidget::item:selected { background-color: #0e3538; color: #2dd4bf; font-weight: 700; }"
        )
        left_layout.addWidget(self.seller_list, 1)

        list_actions = QHBoxLayout()
        self.btn_add_seller = QPushButton("+ Add Seller")
        self.btn_add_seller.setObjectName("primaryButton")
        self.btn_add_seller.setCursor(Qt.PointingHandCursor)

        self.btn_remove_seller = QPushButton("Remove")
        self.btn_remove_seller.setObjectName("destructiveButton")
        self.btn_remove_seller.setCursor(Qt.PointingHandCursor)

        list_actions.addWidget(self.btn_add_seller)
        list_actions.addWidget(self.btn_remove_seller)
        left_layout.addLayout(list_actions)

        body_layout.addWidget(left_card)

        # ---------------- Right Panel: Configuration Form ----------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setStyleSheet("background: transparent;")

        form_container = QWidget()
        form_vbox = QVBoxLayout(form_container)
        form_vbox.setContentsMargins(0, 0, 0, 0)
        form_vbox.setSpacing(14)

        # Group 1: Store Identity
        group_identity = QFrame()
        group_identity.setObjectName("panel")
        id_layout = QVBoxLayout(group_identity)
        id_layout.setContentsMargins(18, 16, 18, 16)
        id_layout.setSpacing(10)

        self.lbl_sec_identity = QLabel("Store Identity")
        self.lbl_sec_identity.setObjectName("sectionTitle")
        id_layout.addWidget(self.lbl_sec_identity)

        id_form = QFormLayout()
        id_form.setSpacing(10)
        self.input_seller_id = QLineEdit()
        self.input_seller_id.setPlaceholderText("Digits only (e.g. 123456)")
        self.input_seller_name = QLineEdit()
        self.input_seller_name.setPlaceholderText("Store display name (e.g. My Trendyol Store)")

        self.lbl_f_seller_id = QLabel("Seller ID:")
        self.lbl_f_seller_name = QLabel("Seller Name:")
        id_form.addRow(self.lbl_f_seller_id, self.input_seller_id)
        id_form.addRow(self.lbl_f_seller_name, self.input_seller_name)
        id_layout.addLayout(id_form)
        form_vbox.addWidget(group_identity)

        # Group 2: Trendyol API Access
        group_api = QFrame()
        group_api.setObjectName("panel")
        api_layout = QVBoxLayout(group_api)
        api_layout.setContentsMargins(18, 16, 18, 16)
        api_layout.setSpacing(10)

        self.lbl_sec_api = QLabel("Trendyol API Credentials (Encrypted with Windows DPAPI)")
        self.lbl_sec_api.setObjectName("sectionTitle")
        api_layout.addWidget(self.lbl_sec_api)

        api_form = QFormLayout()
        api_form.setSpacing(10)

        self.input_api_key = QLineEdit()
        self.input_api_key.setEchoMode(QLineEdit.Password)
        self.input_api_key.setPlaceholderText("Required for a new seller; blank keeps the saved key")

        self.input_api_secret = QLineEdit()
        self.input_api_secret.setEchoMode(QLineEdit.Password)
        self.input_api_secret.setPlaceholderText("Required for a new seller; blank keeps the saved secret")

        self.lbl_f_api_key = QLabel("API Key:")
        self.lbl_f_api_secret = QLabel("API Secret:")
        api_form.addRow(self.lbl_f_api_key, self.input_api_key)
        api_form.addRow(self.lbl_f_api_secret, self.input_api_secret)

        self.lbl_crypto_hint = QLabel(
            "🔒 Keys are encrypted at rest using your Windows account. Plain text secrets are never logged or stored."
        )
        self.lbl_crypto_hint.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        api_layout.addLayout(api_form)
        api_layout.addWidget(self.lbl_crypto_hint)
        form_vbox.addWidget(group_api)

        # Group 3: Cargo & Hardware Fulfillment
        group_fulfillment = QFrame()
        group_fulfillment.setObjectName("panel")
        ful_layout = QVBoxLayout(group_fulfillment)
        ful_layout.setContentsMargins(18, 16, 18, 16)
        ful_layout.setSpacing(10)

        self.lbl_sec_fulfillment = QLabel("Fulfillment & Physical Thermal Printing")
        self.lbl_sec_fulfillment.setObjectName("sectionTitle")
        ful_layout.addWidget(self.lbl_sec_fulfillment)

        ful_form = QFormLayout()
        ful_form.setSpacing(10)

        self.combo_cargo = QComboBox()
        for code, label in CARGO_PROVIDERS.items():
            self.combo_cargo.addItem(label, code)

        self.combo_printer = QComboBox()
        self._refresh_printers()

        self.lbl_f_cargo = QLabel("Default Cargo:")
        self.lbl_f_printer = QLabel("Printer:")
        ful_form.addRow(self.lbl_f_cargo, self.combo_cargo)
        ful_form.addRow(self.lbl_f_printer, self.combo_printer)

        self.check_auto_switch = QCheckBox("Enable Auto-Switch Cargo on Failure")
        self.check_monitoring = QCheckBox("Enable order monitoring")
        self.check_auto_print = QCheckBox("Print labels automatically")
        self.check_auto_print.setChecked(True)

        ful_form.addRow("", self.check_auto_switch)
        ful_form.addRow("", self.check_monitoring)
        ful_form.addRow("", self.check_auto_print)

        ful_layout.addLayout(ful_form)
        form_vbox.addWidget(group_fulfillment)

        # Actions Card
        actions_card = QFrame()
        actions_card.setObjectName("panel")
        actions_layout = QHBoxLayout(actions_card)
        actions_layout.setContentsMargins(18, 14, 18, 14)
        actions_layout.setSpacing(12)

        self.btn_test_credentials = QPushButton("Validate Configuration")
        self.btn_test_credentials.setObjectName("ghostButton")
        self.btn_test_credentials.setCursor(Qt.PointingHandCursor)
        self.btn_test_credentials.clicked.connect(self._validate_current_form)

        self.btn_save = QPushButton("Save Seller Configuration")
        self.btn_save.setObjectName("primaryButton")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_seller)

        actions_layout.addWidget(self.btn_test_credentials)
        actions_layout.addStretch()
        actions_layout.addWidget(self.btn_save)

        form_vbox.addWidget(actions_card)
        form_vbox.addStretch()

        right_scroll.setWidget(form_container)
        body_layout.addWidget(right_scroll, 1)

        root_layout.addLayout(body_layout, 1)

        # Wire Signals
        self.seller_list.currentItemChanged.connect(self._select_seller)
        self.btn_add_seller.clicked.connect(self._new_seller)
        self.btn_remove_seller.clicked.connect(self._delete_seller)

        if self.seller_manager is not None:
            self.refresh_sellers()
        self.set_language("en")

    def set_language(self, language: str) -> None:
        self.language = language
        self.header.set_language(language)
        self.lbl_stores_title.setText(tr("Connected Stores", language))
        self.btn_add_seller.setText(tr("Add New Seller", language))
        self.btn_remove_seller.setText(tr("Remove Selected", language))
        self.lbl_sec_identity.setText(tr("Store Identity", language))
        self.lbl_f_seller_id.setText(tr("Seller ID:", language))
        self.lbl_f_seller_name.setText(tr("Seller Name:", language))
        self.input_seller_id.setPlaceholderText(tr("Digits only", language))
        self.lbl_sec_api.setText(tr("Trendyol API Credentials (Encrypted with Windows DPAPI)", language))
        self.lbl_f_api_key.setText(tr("API Key:", language))
        self.lbl_f_api_secret.setText(tr("API Secret:", language))
        self.input_api_key.setPlaceholderText(
            tr("Required for a new seller; blank keeps the saved key", language)
        )
        self.input_api_secret.setPlaceholderText(
            tr("Required for a new seller; blank keeps the saved secret", language)
        )
        self.lbl_crypto_hint.setText(
            tr("🔒 Keys are encrypted at rest using your Windows account. Plain text secrets are never logged or stored.", language)
        )
        self.lbl_sec_fulfillment.setText(tr("Fulfillment & Physical Thermal Printing", language))
        self.lbl_f_cargo.setText(tr("Default Cargo:", language))
        self.lbl_f_printer.setText(tr("Printer:", language))
        self.check_auto_switch.setText(tr("Enable Auto-Switch Cargo on Failure", language))
        self.check_monitoring.setText(tr("Enable order monitoring", language))
        self.check_auto_print.setText(tr("Print labels automatically", language))
        self.btn_test_credentials.setText(tr("Validate Configuration", language))
        self.btn_save.setText(tr("Save Seller Configuration", language))

        selected_cargo = self.combo_cargo.currentData()
        self.combo_cargo.clear()
        for code, label in CARGO_PROVIDERS.items():
            self.combo_cargo.addItem(tr(label, language), code)
        index = self.combo_cargo.findData(selected_cargo)
        self.combo_cargo.setCurrentIndex(max(0, index))
        self._refresh_printers()

    def _refresh_printers(self, selected: Optional[str] = None) -> None:
        if selected is None and hasattr(self, "combo_printer"):
            selected = self.combo_printer.currentData()
        self.combo_printer.clear()
        self.combo_printer.addItem(
            tr("Use system default printer", self.language),
            "",
        )
        for printer in sorted(
            QPrinterInfo.availablePrinters(),
            key=lambda item: item.printerName().casefold(),
        ):
            name = printer.printerName()
            self.combo_printer.addItem(name, name)
        index = self.combo_printer.findData(selected or "")
        self.combo_printer.setCurrentIndex(max(0, index))

    def set_manager(self, seller_manager: SellerManager) -> None:
        self.seller_manager = seller_manager
        self.refresh_sellers()

    def refresh_sellers(self, select_seller_id=None) -> None:
        self.seller_list.clear()
        selected_row = -1
        profiles = self.seller_manager.list_all() if self.seller_manager else []
        for index, profile in enumerate(profiles):
            status = self._seller_status.get(profile.seller_id, "Idle")
            icon = "● " if profile.is_active and profile.monitoring_enabled else "○ "
            self.seller_list.addItem(f"{icon}{profile.display_tag} ({profile.seller_id})")
            list_item = self.seller_list.item(index)
            list_item.setData(Qt.UserRole, profile.seller_id)
            list_item.setToolTip(f"{tr('Status', self.language)}: {status}")
            if profile.seller_id == select_seller_id:
                selected_row = index

        if selected_row >= 0:
            self.seller_list.setCurrentRow(selected_row)
        elif self.seller_list.count():
            self.seller_list.setCurrentRow(0)
        else:
            self._new_seller()

    def _select_seller(self, current, _previous) -> None:
        if current is None or not self.seller_manager:
            return
        profile = self.seller_manager.get(current.data(Qt.UserRole))
        if profile is None:
            return

        self._selected_seller_id = profile.seller_id
        self.input_seller_id.setText(profile.seller_id)
        self.input_seller_id.setEnabled(False)
        self.input_seller_name.setText(profile.name)
        self.input_api_key.clear()
        self.input_api_secret.clear()
        self.combo_cargo.setCurrentIndex(
            max(0, self.combo_cargo.findData(profile.preferred_cargo))
        )
        self.check_auto_switch.setChecked(profile.cargo_switch_enabled)
        self.check_monitoring.setChecked(profile.monitoring_enabled)
        self.check_auto_print.setChecked(profile.auto_print)
        self._refresh_printers(profile.printer_name)

    def _new_seller(self) -> None:
        self.seller_list.clearSelection()
        self.seller_list.setCurrentRow(-1)
        self._selected_seller_id = None
        self.input_seller_id.clear()
        self.input_seller_id.setEnabled(True)
        self.input_seller_name.clear()
        self.input_api_key.clear()
        self.input_api_secret.clear()
        self.combo_cargo.setCurrentIndex(0)
        self.check_auto_switch.setChecked(True)
        self.check_monitoring.setChecked(True)
        self.check_auto_print.setChecked(True)
        self._refresh_printers("")

    def _validate_current_form(self) -> None:
        seller_id = self.input_seller_id.text().strip()
        old_profile = self.seller_manager.get(self._selected_seller_id) if self._selected_seller_id and self.seller_manager else None

        profile = SellerProfile(
            seller_id=seller_id,
            name=self.input_seller_name.text().strip(),
            api_key=self.input_api_key.text() or (old_profile.api_key if old_profile else ""),
            api_secret=self.input_api_secret.text() or (old_profile.api_secret if old_profile else ""),
            preferred_cargo=self.combo_cargo.currentData(),
            printer_name=self.combo_printer.currentData() or "",
            cargo_switch_enabled=self.check_auto_switch.isChecked(),
            monitoring_enabled=self.check_monitoring.isChecked(),
            auto_print=self.check_auto_print.isChecked(),
        )

        errors = self.seller_manager.validate_profile(profile) if self.seller_manager else []
        cred_error = profile.credential_error
        if cred_error and cred_error not in errors:
            errors.append(cred_error)

        if errors:
            QMessageBox.warning(
                self,
                tr("Validation Failed", self.language),
                "\n".join(tr(err, self.language) for err in errors),
            )
        else:
            QMessageBox.information(
                self,
                tr("Validation Passed", self.language),
                tr("Configuration and credentials format are valid and ready to save.", self.language),
            )

    def _save_seller(self) -> None:
        if not self.seller_manager:
            return
        seller_id = self.input_seller_id.text().strip()
        old_profile = self.seller_manager.get(self._selected_seller_id) if self._selected_seller_id else None
        if old_profile is None and self.seller_manager.get(seller_id) is not None:
            QMessageBox.warning(
                self,
                tr("Seller configuration", self.language),
                tr("A seller with this ID already exists. Select it to edit the saved profile.", self.language),
            )
            return

        profile = SellerProfile(
            seller_id=seller_id,
            name=self.input_seller_name.text().strip(),
            api_key=self.input_api_key.text() or (old_profile.api_key if old_profile else ""),
            api_secret=self.input_api_secret.text() or (old_profile.api_secret if old_profile else ""),
            preferred_cargo=self.combo_cargo.currentData(),
            printer_name=self.combo_printer.currentData() or "",
            cargo_switch_enabled=self.check_auto_switch.isChecked(),
            monitoring_enabled=self.check_monitoring.isChecked(),
            auto_print=self.check_auto_print.isChecked(),
        )
        try:
            errors = self.seller_manager.save_profile(profile)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                tr("Seller configuration", self.language),
                tr("Could not save seller:\n{error}", self.language).format(error=exc),
            )
            return
        if errors:
            QMessageBox.warning(
                self,
                tr("Seller configuration", self.language),
                "\n".join(tr(error, self.language) for error in errors),
            )
            return

        self.refresh_sellers(seller_id)
        self.seller_configuration_changed.emit()
        QMessageBox.information(
            self,
            tr("Seller configuration", self.language),
            tr("Seller configuration saved.", self.language),
        )

    def set_seller_status(self, seller_id: str, status: str) -> None:
        self._seller_status[seller_id] = status
        for index in range(self.seller_list.count()):
            item = self.seller_list.item(index)
            if item.data(Qt.UserRole) == seller_id:
                item.setToolTip(f"{tr('Status', self.language)}: {status}")
                break

    def _delete_seller(self) -> None:
        seller_id = self._selected_seller_id
        if not seller_id or not self.seller_manager:
            QMessageBox.information(
                self,
                tr("Remove seller", self.language),
                tr("Select a seller to remove.", self.language),
            )
            return

        if not ask_yes_no(
            self,
            "Remove seller",
            "Remove seller {seller_id}?",
            self.language,
            seller_id=seller_id,
        ):
            return

        try:
            self.seller_manager.delete_profile(seller_id)
        except OSError as exc:
            QMessageBox.critical(
                self,
                tr("Remove seller", self.language),
                tr("Could not remove seller:\n{error}", self.language).format(error=exc),
            )
            return
        self._seller_status.pop(seller_id, None)
        self.refresh_sellers()
        self.seller_configuration_changed.emit()
