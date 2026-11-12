from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.seller_models import CARGO_PROVIDERS, SellerProfile
from core.seller_manager import SellerManager

class SellersTab(QWidget):
    seller_configuration_changed = Signal()

    def __init__(self, seller_manager=None):
        super().__init__()
        self.seller_manager = seller_manager
        self._selected_seller_id = None
        self._seller_status = {}
        layout = QHBoxLayout(self)

        # Left Panel: List of Sellers
        left_panel = QVBoxLayout()
        self.seller_list = QListWidget()
        self.btn_add_seller = QPushButton("Add New Seller")
        self.btn_remove_seller = QPushButton("Remove Selected")
        
        left_panel.addWidget(self.seller_list)
        left_panel.addWidget(self.btn_add_seller)
        left_panel.addWidget(self.btn_remove_seller)
        layout.addLayout(left_panel, 1)

        # Right Panel: Seller Configuration Form
        right_panel = QVBoxLayout()
        form_layout = QFormLayout()

        self.input_seller_name = QLineEdit()
        self.input_seller_id = QLineEdit()
        self.input_seller_id.setPlaceholderText("Digits only")
        self.input_api_key = QLineEdit()
        self.input_api_key.setEchoMode(QLineEdit.Password)
        self.input_api_key.setPlaceholderText("Required for a new seller; blank keeps the saved key")
        self.input_api_secret = QLineEdit()
        self.input_api_secret.setEchoMode(QLineEdit.Password)
        self.input_api_secret.setPlaceholderText("Required for a new seller; blank keeps the saved secret")
        
        self.combo_cargo = QComboBox()
        for code, label in CARGO_PROVIDERS.items():
            self.combo_cargo.addItem(label, code)
        
        self.check_auto_switch = QCheckBox("Enable Auto-Switch Cargo on Failure")
        self.check_monitoring = QCheckBox("Enable order monitoring")
        self.check_auto_print = QCheckBox("Print labels automatically")
        self.check_auto_print.setChecked(True)

        form_layout.addRow("Seller ID:", self.input_seller_id)
        form_layout.addRow("Seller Name:", self.input_seller_name)
        form_layout.addRow("API Key:", self.input_api_key)
        form_layout.addRow("API Secret:", self.input_api_secret)
        form_layout.addRow("Default Cargo:", self.combo_cargo)
        form_layout.addRow("", self.check_auto_switch)
        form_layout.addRow("", self.check_monitoring)
        form_layout.addRow("", self.check_auto_print)

        self.btn_save = QPushButton("Save Seller Configuration")
        
        right_panel.addLayout(form_layout)
        right_panel.addWidget(self.btn_save)
        right_panel.addStretch()
        
        layout.addLayout(right_panel, 2)

        self.seller_list.currentItemChanged.connect(self._select_seller)
        self.btn_add_seller.clicked.connect(self._new_seller)
        self.btn_remove_seller.clicked.connect(self._delete_seller)
        self.btn_save.clicked.connect(self._save_seller)

        if self.seller_manager is not None:
            self.refresh_sellers()

    def set_manager(self, seller_manager: SellerManager) -> None:
        self.seller_manager = seller_manager
        self.refresh_sellers()

    def refresh_sellers(self, select_seller_id=None) -> None:
        self.seller_list.clear()
        selected_row = -1
        for index, profile in enumerate(self.seller_manager.list_all()):
            self.seller_list.addItem(f"{profile.display_tag} ({profile.seller_id})")
            list_item = self.seller_list.item(index)
            list_item.setData(Qt.UserRole, profile.seller_id)
            if profile.seller_id in self._seller_status:
                list_item.setToolTip(self._seller_status[profile.seller_id])
            if profile.seller_id == select_seller_id:
                selected_row = index

        if selected_row >= 0:
            self.seller_list.setCurrentRow(selected_row)
        elif self.seller_list.count():
            self.seller_list.setCurrentRow(0)
        else:
            self._new_seller()

    def _select_seller(self, current, _previous) -> None:
        if current is None:
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

    def _save_seller(self) -> None:
        seller_id = self.input_seller_id.text().strip()
        old_profile = self.seller_manager.get(self._selected_seller_id) if self._selected_seller_id else None
        if old_profile is None and self.seller_manager.get(seller_id) is not None:
            QMessageBox.warning(
                self,
                "Seller configuration",
                "A seller with this ID already exists. Select it to edit the saved profile.",
            )
            return
        profile = SellerProfile(
            seller_id=seller_id,
            name=self.input_seller_name.text().strip(),
            api_key=self.input_api_key.text() or (old_profile.api_key if old_profile else ""),
            api_secret=self.input_api_secret.text() or (old_profile.api_secret if old_profile else ""),
            preferred_cargo=self.combo_cargo.currentData(),
            cargo_switch_enabled=self.check_auto_switch.isChecked(),
            monitoring_enabled=self.check_monitoring.isChecked(),
            auto_print=self.check_auto_print.isChecked(),
        )
        try:
            errors = self.seller_manager.save_profile(profile)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Seller configuration", f"Could not save seller:\n{exc}")
            return
        if errors:
            QMessageBox.warning(self, "Seller configuration", "\n".join(errors))
            return

        self.refresh_sellers(seller_id)
        self.seller_configuration_changed.emit()
        QMessageBox.information(self, "Seller configuration", "Seller configuration saved.")

    def set_seller_status(self, seller_id: str, status: str) -> None:
        self._seller_status[seller_id] = status
        for index in range(self.seller_list.count()):
            item = self.seller_list.item(index)
            if item.data(Qt.UserRole) == seller_id:
                item.setToolTip(status)
                break

    def _delete_seller(self) -> None:
        seller_id = self._selected_seller_id
        if not seller_id:
            QMessageBox.information(self, "Remove seller", "Select a seller to remove.")
            return

        answer = QMessageBox.question(
            self,
            "Remove seller",
            f"Remove seller {seller_id}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            self.seller_manager.delete_profile(seller_id)
        except OSError as exc:
            QMessageBox.critical(self, "Remove seller", f"Could not remove seller:\n{exc}")
            return
        self._seller_status.pop(seller_id, None)
        self.refresh_sellers()
        self.seller_configuration_changed.emit()