"""Dedicated settings and configuration tab for the Luma desktop application."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.paths import get_data_dir, get_data_path
from core.version import VERSION
from ui_components import SectionHeader, StatusBadge


class SettingsTab(QWidget):
    """Organized application settings for appearance, thermal layout, data, and updates."""

    language_changed = Signal(str)
    check_updates_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.settings = QSettings("Luma", "Luma")
        saved_lang = self.settings.value("language", "en")
        self.language = saved_lang if saved_lang in ("en", "tr") else "en"

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(14)

        self.header = SectionHeader(
            title="Application Settings & Preferences",
            subtitle="Configure local preferences, hardware printing defaults, data backups, and updates.",
        )
        root_layout.addWidget(self.header)

        # Scrollable container for settings groups
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # ---------------- Section 1: General & Localization ----------------
        card_general = QFrame()
        card_general.setObjectName("panel")
        cg_layout = QVBoxLayout(card_general)
        cg_layout.setContentsMargins(18, 16, 18, 16)
        cg_layout.setSpacing(12)

        self.lbl_sec_general = QLabel("General & Localization")
        self.lbl_sec_general.setObjectName("sectionTitle")
        cg_layout.addWidget(self.lbl_sec_general)

        lang_row = QHBoxLayout()
        self.lbl_language = QLabel("Application Language:")
        self.lbl_language.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        self.combo_language = QComboBox()
        self.combo_language.addItem("English", "en")
        self.combo_language.addItem("Türkçe", "tr")
        lang_idx = self.combo_language.findData(self.language)
        self.combo_language.setCurrentIndex(max(0, lang_idx))
        self.combo_language.currentIndexChanged.connect(self._on_language_changed)

        lang_row.addWidget(self.lbl_language)
        lang_row.addWidget(self.combo_language, 1)
        cg_layout.addLayout(lang_row)

        self.check_auto_update_startup = QCheckBox("Check for software updates automatically at startup")
        self.check_auto_update_startup.setChecked(
            self.settings.value("auto_check_updates", True, type=bool)
        )
        self.check_auto_update_startup.toggled.connect(
            lambda val: self.settings.setValue("auto_check_updates", val)
        )
        cg_layout.addWidget(self.check_auto_update_startup)
        layout.addWidget(card_general)

        # ---------------- Section 2: Thermal Printing Defaults ----------------
        card_print = QFrame()
        card_print.setObjectName("panel")
        cp_layout = QVBoxLayout(card_print)
        cp_layout.setContentsMargins(18, 16, 18, 16)
        cp_layout.setSpacing(12)

        self.lbl_sec_print = QLabel("Thermal Printer & Hardware Defaults")
        self.lbl_sec_print.setObjectName("sectionTitle")
        cp_layout.addWidget(self.lbl_sec_print)

        size_row = QHBoxLayout()
        self.lbl_label_size = QLabel("Default Thermal Label Size:")
        self.lbl_label_size.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        self.combo_default_size = QComboBox()
        self.combo_default_size.addItem("100x100 mm (Standard)", "100x100")
        self.combo_default_size.addItem("100x150 mm (Extended)", "100x150")
        saved_size = self.settings.value("default_label_size", "100x100")
        idx_size = self.combo_default_size.findData(saved_size)
        self.combo_default_size.setCurrentIndex(max(0, idx_size))
        self.combo_default_size.currentIndexChanged.connect(
            lambda: self.settings.setValue("default_label_size", self.combo_default_size.currentData())
        )
        size_row.addWidget(self.lbl_label_size)
        size_row.addWidget(self.combo_default_size, 1)
        cp_layout.addLayout(size_row)

        shift_row = QHBoxLayout()
        self.lbl_shift = QLabel("Default Vertical Shift Y (mm):")
        self.lbl_shift.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        self.spin_shift = QDoubleSpinBox()
        self.spin_shift.setRange(0.0, 150.0)
        self.spin_shift.setValue(self.settings.value("default_shift_y", 29.0, type=float))
        self.spin_shift.valueChanged.connect(
            lambda val: self.settings.setValue("default_shift_y", val)
        )
        shift_row.addWidget(self.lbl_shift)
        shift_row.addWidget(self.spin_shift, 1)
        cp_layout.addLayout(shift_row)

        layout.addWidget(card_print)

        # ---------------- Section 3: Data & Backups ----------------
        card_data = QFrame()
        card_data.setObjectName("panel")
        cd_layout = QVBoxLayout(card_data)
        cd_layout.setContentsMargins(18, 16, 18, 16)
        cd_layout.setSpacing(12)

        self.lbl_sec_data = QLabel("Data Persistence & Automated Backups")
        self.lbl_sec_data.setObjectName("sectionTitle")
        cd_layout.addWidget(self.lbl_sec_data)

        path_row = QHBoxLayout()
        self.lbl_data_dir = QLabel("Application Data Directory:")
        self.lbl_data_dir.setStyleSheet("font-weight: 600; color: #cbd5e1;")
        self.txt_data_dir = QLineEdit(str(get_data_dir()))
        self.txt_data_dir.setReadOnly(True)
        path_row.addWidget(self.lbl_data_dir)
        path_row.addWidget(self.txt_data_dir, 1)
        cd_layout.addLayout(path_row)

        btn_row = QHBoxLayout()
        self.btn_open_data_folder = QPushButton("Open Data Folder")
        self.btn_open_data_folder.setObjectName("ghostButton")
        self.btn_open_data_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_data_folder.clicked.connect(self._open_data_folder)

        self.btn_open_logs_folder = QPushButton("Open Logs Folder")
        self.btn_open_logs_folder.setObjectName("ghostButton")
        self.btn_open_logs_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_logs_folder.clicked.connect(self._open_logs_folder)

        self.btn_backup_now = QPushButton("Create Backup Now")
        self.btn_backup_now.setObjectName("primaryButton")
        self.btn_backup_now.setCursor(Qt.PointingHandCursor)
        self.btn_backup_now.clicked.connect(self._create_manual_backup)

        btn_row.addWidget(self.btn_open_data_folder)
        btn_row.addWidget(self.btn_open_logs_folder)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_backup_now)
        cd_layout.addLayout(btn_row)

        self.lbl_retention_info = QLabel(
            "🛡️ Automatic backups are created on every change. The retention policy maintains the last 30 snapshots."
        )
        self.lbl_retention_info.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        cd_layout.addWidget(self.lbl_retention_info)
        layout.addWidget(card_data)

        # ---------------- Section 4: Software Updates & About ----------------
        card_about = QFrame()
        card_about.setObjectName("panel")
        ca_layout = QVBoxLayout(card_about)
        ca_layout.setContentsMargins(18, 16, 18, 16)
        ca_layout.setSpacing(12)

        self.lbl_sec_about = QLabel("Software Updates & System Information")
        self.lbl_sec_about.setObjectName("sectionTitle")
        ca_layout.addWidget(self.lbl_sec_about)

        ver_row = QHBoxLayout()
        self.lbl_version_title = QLabel(f"Luma Trendyol Manager — Version {VERSION}")
        self.lbl_version_title.setStyleSheet("font-weight: 700; font-size: 11pt; color: #f8fafc;")

        self.badge_ver = StatusBadge(f"v{VERSION}", "info")

        self.btn_check_updates = QPushButton("Check for Updates")
        self.btn_check_updates.setObjectName("ghostButton")
        self.btn_check_updates.setCursor(Qt.PointingHandCursor)
        self.btn_check_updates.clicked.connect(lambda: self.check_updates_requested.emit())

        ver_row.addWidget(self.lbl_version_title)
        ver_row.addWidget(self.badge_ver)
        ver_row.addStretch()
        ver_row.addWidget(self.btn_check_updates)
        ca_layout.addLayout(ver_row)

        self.lbl_about_desc = QLabel(
            "High-reliability multi-seller management, automated cargo provider switching, "
            "and direct thermal label printing for Trendyol e-commerce sellers."
        )
        self.lbl_about_desc.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
        ca_layout.addWidget(self.lbl_about_desc)
        layout.addWidget(card_about)

        layout.addStretch()
        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        self.set_language(self.language)

    def set_language(self, language: str) -> None:
        self.language = language
        self.header.set_language(language)
        self.lbl_sec_general.setText(tr("General & Localization", language))
        self.lbl_language.setText(tr("Application Language:", language))
        self.check_auto_update_startup.setText(tr("Check for software updates automatically at startup", language))
        self.lbl_sec_print.setText(tr("Thermal Printer & Hardware Defaults", language))
        self.lbl_label_size.setText(tr("Default Thermal Label Size:", language))
        self.lbl_shift.setText(tr("Default Vertical Shift Y (mm):", language))
        self.lbl_sec_data.setText(tr("Data Persistence & Automated Backups", language))
        self.lbl_data_dir.setText(tr("Application Data Directory:", language))
        self.btn_open_data_folder.setText(tr("Open Data Folder", language))
        self.btn_open_logs_folder.setText(tr("Open Logs Folder", language))
        self.btn_backup_now.setText(tr("Create Backup Now", language))
        self.lbl_retention_info.setText(
            tr("🛡️ Automatic backups are created on every change. The retention policy maintains the last 30 snapshots.", language)
        )
        self.lbl_sec_about.setText(tr("Software Updates & System Information", language))
        self.btn_check_updates.setText(tr("Check for Updates", language))
        self.lbl_about_desc.setText(
            tr("High-reliability multi-seller management, automated cargo provider switching, and direct thermal label printing for Trendyol e-commerce sellers.", language)
        )

    def _on_language_changed(self) -> None:
        selected = self.combo_language.currentData()
        if selected in ("en", "tr"):
            self.language = selected
            self.settings.setValue("language", selected)
            self.set_language(selected)
            self.language_changed.emit(selected)

    def _open_data_folder(self) -> None:
        data_dir = str(get_data_dir())
        try:
            if sys.platform.startswith("win"):
                os.startfile(data_dir)
            else:
                subprocess.Popen(["xdg-open", data_dir])
        except Exception as exc:
            QMessageBox.warning(self, tr("Open Folder", self.language), str(exc))

    def _open_logs_folder(self) -> None:
        log_dir = str(get_data_dir())
        try:
            if sys.platform.startswith("win"):
                os.startfile(log_dir)
            else:
                subprocess.Popen(["xdg-open", log_dir])
        except Exception as exc:
            QMessageBox.warning(self, tr("Open Folder", self.language), str(exc))

    def _create_manual_backup(self) -> None:
        data_dir = get_data_dir()
        backup_dir = data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backed_up = []

        for fname in ("products.json", "data/sellers.json", "printed_packages.json"):
            src = data_dir / fname
            if src.is_file():
                stem = src.stem
                dst = backup_dir / f"{stem}_manual_{ts}.json"
                try:
                    shutil.copy2(src, dst)
                    backed_up.append(src.name)
                except OSError:
                    pass

        if backed_up:
            QMessageBox.information(
                self,
                tr("Backup Complete", self.language),
                tr("Created snapshot backup for: {files}\nSaved in:\n{dir}", self.language).format(
                    files=", ".join(backed_up), dir=backup_dir
                ),
            )
        else:
            QMessageBox.information(
                self,
                tr("Backup", self.language),
                tr("No active data files were found to back up.", self.language),
            )
