"""Main application window, persistent navigation, and coordinator for Luma."""
from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QTimer, Signal, Qt
from PySide6.QtGui import QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app_controller import AppController
from core.i18n import ask_yes_no, tr
from core.paths import is_frozen
from core.updates import (
    UpdateRelease,
    download_update,
    get_latest_release,
    install_update,
    launch_update,
)
from core.version import VERSION
from ui_catalog import CatalogTab
from ui_components import StatusBadge
from ui_dashboard import DashboardTab
from ui_logs import LogsTab
from ui_orders import OrdersTab
from ui_reports import ReportsTab
from ui_sellers import SellersTab
from ui_settings import SettingsTab
from ui_theme import DARK_STYLESHEET


class _ReleaseCheckWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.completed.emit(get_latest_release(VERSION))
        except Exception as exc:
            self.failed.emit(str(exc))


class _UpdateDownloadWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, release: UpdateRelease):
        super().__init__()
        self.release = release

    def run(self):
        try:
            staged_executable = download_update(self.release)
            self.completed.emit(
                install_update(staged_executable, self.release.version)
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class LumaMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Luma", "Luma")
        saved_language = self.settings.value("language", "en")
        self.language = saved_language if saved_language in ("en", "tr") else "en"
        self.resize(1440, 900)
        self.setMinimumSize(1080, 720)
        self.setStyleSheet(DARK_STYLESHEET)

        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        # ---------------- Left Navigation Sidebar ----------------
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(240)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(16, 22, 16, 18)
        side.setSpacing(6)

        # Brand mark & app title
        brand_row = QHBoxLayout()
        mark = QLabel("◈")
        mark.setObjectName("brandMark")
        brand = QLabel("Luma")
        brand.setObjectName("brand")
        brand_row.addWidget(mark)
        brand_row.addWidget(brand)
        brand_row.addStretch()
        side.addLayout(brand_row)

        self.tagline = QLabel("COMMERCIAL OPERATIONS SUITE")
        self.tagline.setObjectName("tagline")
        side.addWidget(self.tagline)
        side.addSpacing(20)

        # Navigation tabs
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)

        self.tab_dashboard = DashboardTab()
        self.tab_orders = OrdersTab()
        self.tab_sellers = SellersTab()
        self.tab_catalog = CatalogTab()
        self.tab_reports = ReportsTab()
        self.tab_logs = LogsTab()
        self.tab_settings = SettingsTab()

        self._pages = [
            ("⌂", "Overview", self.tab_dashboard),
            ("▣", "Orders & Labels", self.tab_orders),
            ("♙", "Seller Config", self.tab_sellers),
            ("▦", "Product Catalog", self.tab_catalog),
            ("📈", "Reports", self.tab_reports),
            ("▤", "System Logs", self.tab_logs),
            ("⚙", "Settings", self.tab_settings),
        ]

        self.nav_buttons = []
        for icon, title, page in self._pages:
            self.tabs.addTab(page, title)
            button = QPushButton(f"{icon}   {title}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(partial(self.navigate, len(self.nav_buttons)))
            side.addWidget(button)
            self.nav_buttons.append(button)

        side.addStretch()

        # System health status pill in sidebar
        health = QFrame()
        health.setObjectName("systemPill")
        health_layout = QVBoxLayout(health)
        health_layout.setContentsMargins(12, 10, 12, 10)
        health_layout.setSpacing(4)

        pill_top = QHBoxLayout()
        self.health_title = QLabel("SYSTEM READY")
        self.health_title.setObjectName("accent")
        self.status_pill_badge = StatusBadge("ACTIVE", "success")
        pill_top.addWidget(self.health_title)
        pill_top.addStretch()
        pill_top.addWidget(self.status_pill_badge)
        health_layout.addLayout(pill_top)

        self.health_note = QLabel("Luma services")
        self.health_note.setObjectName("muted")
        health_layout.addWidget(self.health_note)
        side.addWidget(health)

        version_label = QLabel(f"Version {VERSION}")
        version_label.setObjectName("muted")
        version_label.setStyleSheet("padding-top: 4px; font-size: 8.5pt;")
        side.addWidget(version_label)

        shell.addWidget(self.sidebar)

        # ---------------- Main Content Area ----------------
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 20, 28, 20)
        content_layout.setSpacing(14)

        # Header Bar
        top = QHBoxLayout()
        self.page_heading = QLabel()
        self.page_heading.setObjectName("pageTitle")
        top.addWidget(self.page_heading)
        top.addStretch()

        # Header quick controls
        self.monitoring_label = QLabel()
        self.monitoring_label.setObjectName("accent")
        top.addWidget(self.monitoring_label)

        content_layout.addLayout(top)

        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self.tabs, 1)
        shell.addWidget(content, 1)

        # Workers & Update Management
        self._release_check_worker = None
        self._update_download_worker = None
        self._release_check_silent = False

        # Menu Bar
        self.language_menu = self.menuBar().addMenu("")
        language_group = QActionGroup(self)
        language_group.setExclusive(True)
        self.language_actions = {}
        for code, label in (("en", "English"), ("tr", "Türkçe")):
            action = self.language_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == self.language)
            language_group.addAction(action)
            action.triggered.connect(
                lambda checked, selected=code: self.set_language(selected) if checked else None
            )
            self.language_actions[code] = action

        self.help_menu = self.menuBar().addMenu("")
        self.update_action = self.help_menu.addAction("")
        self.update_action.triggered.connect(self.check_for_updates)

        # Wire dashboard navigation requests
        self.tab_dashboard.navigate_requested.connect(self.navigate)
        self.tab_settings.language_changed.connect(self.set_language)
        self.tab_settings.check_updates_requested.connect(self.check_for_updates)

        # Setup Keyboard Shortcuts
        self._setup_shortcuts()

        # Initialize Language & Navigation
        self.set_language(self.language)
        self.navigate(0)

        # Application Controller & Worker Startup
        self.controller = None
        try:
            self.controller = AppController(self)
            self.set_monitoring_state(True)
        except (OSError, RuntimeError, ValueError) as exc:
            self.set_monitoring_state(False)
            QMessageBox.critical(
                self,
                tr("Seller configuration error", self.language),
                tr(
                    "The seller configuration could not be loaded. Watching is disabled.\n\n{error}",
                    self.language,
                ).format(error=exc),
            )
            self.tab_sellers.setEnabled(False)

        # AppController initializes/migrates the per-user data directory. Refresh
        # catalog and dashboard afterward so UI sees existing state and products.
        self.tab_catalog.refresh()
        self.tab_dashboard.refresh_metrics()
        self.tab_reports.refresh_report()

        if self.settings.value("auto_check_updates", True, type=bool):
            QTimer.singleShot(1500, self.check_for_updates_on_startup)

    def _setup_shortcuts(self) -> None:
        """Register global keyboard shortcuts for fast commercial navigation."""
        for i in range(min(len(self._pages), 7)):
            QShortcut(QKeySequence(f"Ctrl+{i+1}"), self, partial(self.navigate, i))

        QShortcut(QKeySequence("Ctrl+F"), self, self._on_shortcut_find)
        QShortcut(QKeySequence("Ctrl+R"), self, self._on_shortcut_refresh)
        QShortcut(QKeySequence("Ctrl+,"), self, lambda: self.navigate(6))
        QShortcut(QKeySequence("Esc"), self, self._on_shortcut_escape)

    def _on_shortcut_find(self) -> None:
        curr = self.tabs.currentIndex()
        if curr == 1 and hasattr(self.tab_orders, "search_input"):
            self.tab_orders.search_input.setFocus()
            self.tab_orders.search_input.selectAll()
        elif curr == 3 and hasattr(self.tab_catalog, "search"):
            self.tab_catalog.search.setFocus()
            self.tab_catalog.search.selectAll()
        elif curr == 5 and hasattr(self.tab_logs, "search_input"):
            self.tab_logs.search_input.setFocus()
            self.tab_logs.search_input.selectAll()

    def _on_shortcut_refresh(self) -> None:
        curr = self.tabs.currentIndex()
        if curr == 0:
            self.tab_dashboard.refresh_metrics()
        elif curr == 1:
            self.tab_orders.fetch_orders()
        elif curr == 3:
            self.tab_catalog.refresh()
        elif curr == 4:
            self.tab_reports.refresh_report()

    def _on_shortcut_escape(self) -> None:
        curr = self.tabs.currentIndex()
        if curr == 1 and hasattr(self.tab_orders, "search_input"):
            self.tab_orders.search_input.clear()
        elif curr == 3 and hasattr(self.tab_catalog, "search"):
            self.tab_catalog.search.clear()
        elif curr == 5 and hasattr(self.tab_logs, "search_input"):
            self.tab_logs.search_input.clear()

    def navigate(self, index: int) -> None:
        if index < 0 or index >= len(self._pages):
            return
        self.tabs.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        title = self._pages[index][1]
        self.page_heading.setText(tr(title, self.language))

    def set_monitoring_state(self, active: bool) -> None:
        self.health_title.setText(
            tr("SYSTEM READY" if active else "SYSTEM UNAVAILABLE", self.language)
        )
        self.health_title.setStyleSheet("color: #34d399;" if active else "color: #fbbf24;")
        self.status_pill_badge.set_variant("success" if active else "warning")
        self.status_pill_badge.setText(tr("ACTIVE" if active else "OFFLINE", self.language))
        self.monitoring_label.setText(
            tr("Monitoring active" if active else "Monitoring unavailable", self.language)
        )

    def check_for_updates_on_startup(self) -> None:
        """Check quietly for updates after the packaged application has opened."""
        self.check_for_updates(silent=True)

    def check_for_updates(self, silent: bool = False):
        if not is_frozen():
            if silent:
                return
            QMessageBox.information(
                self,
                tr("Check for updates", self.language),
                tr("Update installation is available in the packaged Windows application.", self.language),
            )
            return

        if self._release_check_worker is not None or self._update_download_worker is not None:
            return

        self._release_check_silent = silent
        self.update_action.setEnabled(False)
        self._release_check_worker = _ReleaseCheckWorker(self)
        self._release_check_worker.completed.connect(self._on_release_checked)
        self._release_check_worker.failed.connect(self._on_update_failed)
        self._release_check_worker.finished.connect(self._on_release_check_finished)
        self._release_check_worker.start()

    def _on_release_check_finished(self):
        self._release_check_worker = None
        if self._update_download_worker is None:
            self.update_action.setEnabled(True)

    def _on_release_checked(self, release):
        if release is None:
            if not self._release_check_silent:
                QMessageBox.information(
                    self,
                    tr("Check for updates", self.language),
                    tr("Luma is up to date (v{version}).", self.language).format(version=VERSION),
                )
            return

        notes = release.notes.strip()[:3000] or "No release notes were provided."
        update_text = tr(
            "{title}\nVersion {version} is available (current: {current}).",
            self.language,
        ).format(title=release.title, version=release.version, current=VERSION)
        prompt_text = tr(
            "{notes}\n\nDownload and install this update?",
            self.language,
        ).format(notes=f"{update_text}\n\n{notes}")
        if not ask_yes_no(
            self,
            "Luma update available",
            "{prompt}",
            self.language,
            prompt=prompt_text,
        ):
            return

        self.menuBar().setEnabled(False)
        self._update_download_worker = _UpdateDownloadWorker(release)
        self._update_download_worker.completed.connect(self._on_update_downloaded)
        self._update_download_worker.failed.connect(self._on_update_failed)
        self._update_download_worker.finished.connect(self._on_update_download_finished)
        self._update_download_worker.start()

    def _on_update_download_finished(self):
        self._update_download_worker = None
        self.menuBar().setEnabled(True)

    def _on_update_downloaded(self, installed_path):
        answer = ask_yes_no(
            self,
            "Update ready",
            "The update is installed in your user folder, and a desktop shortcut was created. Start it now?",
            self.language,
        )
        if not answer:
            QMessageBox.information(
                self,
                tr("Update installed", self.language),
                tr(
                    "The update is installed at:\n{path}\nUse the new Luma shortcut on your desktop to open it.",
                    self.language,
                ).format(path=Path(installed_path)),
            )
            return

        try:
            launch_update(Path(installed_path))
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(
                self,
                tr("Update failed", self.language),
                tr("Could not start the updater:\n{error}", self.language).format(error=exc),
            )
            return
        QApplication.quit()

    def _on_update_failed(self, message):
        if self._release_check_silent and self._update_download_worker is None:
            self.statusBar().showMessage(
                tr("Automatic update check failed", self.language),
                8000,
            )
            return
        QMessageBox.warning(self, tr("Update check failed", self.language), message)

    def set_language(self, language: str) -> None:
        if language not in ("en", "tr"):
            language = "en"
        self.language = language
        self.settings.setValue("language", language)
        self.setWindowTitle(tr("Luma Multi-Seller Manager", language))

        for index, (icon, title, _page) in enumerate(self._pages):
            self.tabs.setTabText(index, tr(title, language))
            self.nav_buttons[index].setText(f"{icon}   {tr(title, language)}")

        curr_title = self._pages[self.tabs.currentIndex()][1]
        self.page_heading.setText(tr(curr_title, language))

        self.tab_dashboard.set_language(language)
        self.tab_orders.set_language(language)
        self.tab_sellers.set_language(language)
        self.tab_catalog.set_language(language)
        self.tab_reports.set_language(language)
        self.tab_logs.set_language(language)
        self.tab_settings.set_language(language)

        self.language_menu.setTitle(tr("Language", language))
        self.help_menu.setTitle(tr("Help", language))
        self.update_action.setText(tr("Check for Updates", language))
        self.tagline.setText(tr("COMMERCIAL OPERATIONS SUITE", language))
        self.health_note.setText(tr("Luma services", language))
        self.set_monitoring_state(
            self.controller is not None if hasattr(self, "controller") else False
        )
        for code, action in self.language_actions.items():
            action.setChecked(code == language)

    def closeEvent(self, event):
        if hasattr(self, "tab_orders") and not self.tab_orders.stop_worker():
            QMessageBox.information(
                self,
                tr("Operation in progress", self.language),
                tr(
                    "The order operation is still running. Please wait for it to finish before closing Luma.",
                    self.language,
                ),
            )
            event.ignore()
            return
        if self.controller is not None:
            self.controller.stop_all_workers()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = LumaMainWindow()
    window.show()
    sys.exit(app.exec())
