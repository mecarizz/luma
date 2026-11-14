"""Main application window, persistent navigation, and coordinator for Luma."""
from __future__ import annotations

import sys
import time
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
from core.paths import get_data_path, is_frozen
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
from ui_theme import DARK_STYLESHEET, apply_dark_palette


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

        self.update_status_button = QPushButton(f"Version {VERSION}")
        self.update_status_button.setObjectName("versionStatus")
        self.update_status_button.setCursor(Qt.PointingHandCursor)
        side.addWidget(self.update_status_button)

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
        self._update_ready_path: Path | None = None
        self._update_ready_release: UpdateRelease | None = None
        self._mandatory_update_pending = False
        self._mandatory_update_enforcing = False
        self.update_status_button.clicked.connect(self._handle_update_status_clicked)
        self._update_check_timer = QTimer(self)
        self._update_check_timer.timeout.connect(
            lambda: self.check_for_updates(silent=True)
        )

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
        self.update_action.triggered.connect(lambda: self.check_for_updates())

        # Wire dashboard navigation requests
        self.tab_dashboard.navigate_requested.connect(self.navigate)
        self.tab_settings.language_changed.connect(self.set_language)
        self.tab_settings.check_updates_requested.connect(self.check_for_updates)
        self.tab_settings.auto_update_checks_changed.connect(
            self._configure_update_schedule
        )
        self.tab_settings.update_interval_changed.connect(
            lambda _hours: self._configure_update_schedule(
                self.settings.value("auto_check_updates", True, type=bool)
            )
        )
        self.tab_orders.operation_finished.connect(self._on_order_operation_finished)

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

        auto_check = self.settings.value("auto_check_updates", True, type=bool)
        self._configure_update_schedule(auto_check)
        if auto_check and is_frozen():
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
        if self.settings.value("auto_check_updates", True, type=bool):
            self.check_for_updates(silent=True)

    def _configure_update_schedule(self, enabled: bool) -> None:
        self._update_check_timer.stop()
        if not enabled or not is_frozen():
            return
        hours = self.settings.value("update_check_interval_hours", 4, type=int)
        if hours not in (2, 4, 8):
            hours = 4
        self._update_check_timer.start(hours * 60 * 60 * 1000)

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
            self.update_status_button.setText(f"Version {VERSION}")
            self.update_status_button.setObjectName("versionStatus")
            self.update_status_button.style().unpolish(self.update_status_button)
            self.update_status_button.style().polish(self.update_status_button)
            if not self._release_check_silent:
                QMessageBox.information(
                    self,
                    tr("Check for updates", self.language),
                    tr("Luma is up to date (v{version}).", self.language).format(version=VERSION),
                )
            return

        self._update_ready_release = release
        installed_path = get_data_path("app") / f"v{release.version}" / "Luma.exe"
        if installed_path.is_file():
            self._update_ready_path = installed_path
            self._set_update_status(release, ready=True)
            self._notify_update_ready()
            return

        self._set_update_status(release, ready=False)
        self.statusBar().showMessage(
            tr("Downloading update v{version} in the background", self.language).format(
                version=release.version
            ),
            15000,
        )
        self._start_update_download(release)

    def _set_update_status(self, release: UpdateRelease, ready: bool) -> None:
        if release.importance_level == 3:
            text = tr("Critical update required: v{version}", self.language).format(
                version=release.version
            )
            object_name = "versionStatusCritical"
        elif ready:
            text = tr("Update ready: v{version}", self.language).format(
                version=release.version
            )
            object_name = (
                "versionStatusImportant"
                if release.importance_level == 2
                else "versionStatus"
            )
        else:
            text = tr("Version {version} (outdated)", self.language).format(
                version=VERSION
            )
            object_name = (
                "versionStatusImportant"
                if release.importance_level == 2
                else "versionStatus"
            )
        self.update_status_button.setText(text)
        self.update_status_button.setObjectName(object_name)
        self.update_status_button.setToolTip(release.notes[:3000])
        self.update_status_button.style().unpolish(self.update_status_button)
        self.update_status_button.style().polish(self.update_status_button)

    def _start_update_download(self, release: UpdateRelease) -> None:
        if self._update_download_worker is not None:
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
        self.update_action.setEnabled(self._release_check_worker is None)

    def _on_update_downloaded(self, installed_path):
        self._update_ready_path = Path(installed_path)
        if self._update_ready_release is None:
            self._update_ready_path = None
            QMessageBox.critical(
                self,
                tr("Update failed", self.language),
                tr(
                    "The downloaded update has no matching release information. Check for updates again.",
                    self.language,
                ),
            )
            return
        self._set_update_status(self._update_ready_release, ready=True)
        self._notify_update_ready()

    def _notify_update_ready(self) -> None:
        release = self._update_ready_release
        if release is None or self._update_ready_path is None:
            return

        if release.importance_level == 3:
            self._mandatory_update_pending = True
            if self.tab_orders.operation_in_progress:
                self.statusBar().showMessage(
                    tr(
                        "Critical update ready. Finish the current order operation; Luma will require the update when safe.",
                        self.language,
                    ),
                    30000,
                )
                return
            self._enforce_mandatory_update()
            return

        if release.importance_level == 1:
            if self.settings.value("normal_update_notified_version", "") != release.version:
                self.settings.setValue("normal_update_notified_version", release.version)
                self.statusBar().showMessage(
                    tr("Update v{version} is ready. Select the version label to restart and update.", self.language).format(
                        version=release.version
                    ),
                    20000,
                )
            return

        now = time.time()
        reminded_version = self.settings.value("important_update_reminder_version", "")
        reminded_at = self.settings.value(
            "important_update_reminder_at", 0.0, type=float
        )
        if (
            reminded_version == release.version
            and now - reminded_at < 24 * 60 * 60
        ):
            return
        self.settings.setValue("important_update_reminder_version", release.version)
        self.settings.setValue("important_update_reminder_at", now)
        if ask_yes_no(
            self,
            tr("Important update", self.language),
            tr(
                "Important update v{version} is ready. Restart Luma now? You can choose later; you will be reminded after 24 hours.",
                self.language,
            ).format(version=release.version),
            self.language,
        ):
            self._restart_with_update()

    def _handle_update_status_clicked(self) -> None:
        if self._update_ready_path is None:
            self.check_for_updates()
            return
        if self._mandatory_update_pending:
            self._enforce_mandatory_update()
            return
        release = self._update_ready_release
        if release is None:
            self.check_for_updates()
            return
        notes = release.notes.strip()[:3000] or tr(
            "No release notes were provided.", self.language
        )
        if ask_yes_no(
            self,
            tr("Update ready", self.language),
            tr(
                "Version {version} is ready to install.\n\n{notes}\n\nRestart Luma now?",
                self.language,
            ).format(version=release.version, notes=notes),
            self.language,
        ):
            self._restart_with_update()

    def _restart_with_update(self) -> None:
        if self._update_ready_path is None:
            return
        try:
            launch_update(self._update_ready_path)
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(
                self,
                tr("Update failed", self.language),
                tr("Could not start the updater:\n{error}", self.language).format(error=exc),
            )
            return
        QApplication.quit()

    def _on_order_operation_finished(self) -> None:
        if self._mandatory_update_pending:
            self._enforce_mandatory_update()

    def _enforce_mandatory_update(self) -> None:
        if (
            not self._mandatory_update_pending
            or self._mandatory_update_enforcing
            or self._update_ready_path is None
        ):
            return
        if self.tab_orders.operation_in_progress:
            return
        if QApplication.activeModalWidget() is not None:
            QTimer.singleShot(1000, self._enforce_mandatory_update)
            return

        self._mandatory_update_enforcing = True
        if self.controller is not None:
            self.controller.pause_watcher()
        self.tabs.setEnabled(False)
        prompt = QMessageBox(self)
        prompt.setIcon(QMessageBox.Icon.Warning)
        prompt.setWindowTitle(tr("Critical update required", self.language))
        prompt.setText(
            tr(
                "Save or finish any work now. This critical update is required before Luma can continue. Select Restart and Update to continue.",
                self.language,
            )
        )
        prompt.setStandardButtons(QMessageBox.StandardButton.Ok)
        prompt.button(QMessageBox.StandardButton.Ok).setText(
            tr("Restart and Update", self.language)
        )
        prompt.setEscapeButton(QMessageBox.StandardButton.NoButton)
        prompt.setWindowFlag(Qt.WindowCloseButtonHint, False)
        prompt.exec()
        self._restart_with_update()
        self._mandatory_update_enforcing = False

    def _on_update_failed(self, message):
        if self._release_check_silent:
            self.statusBar().showMessage(
                tr("Automatic update check failed: {error}", self.language).format(
                    error=message
                ),
                15000,
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
        if self._update_ready_release is None:
            self.update_status_button.setText(f"Version {VERSION}")
        else:
            self._set_update_status(
                self._update_ready_release,
                ready=self._update_ready_path is not None,
            )
        self.set_monitoring_state(
            self.controller is not None if hasattr(self, "controller") else False
        )
        for code, action in self.language_actions.items():
            action.setChecked(code == language)

    def closeEvent(self, event):
        if self._mandatory_update_pending and self._update_ready_path is not None:
            if self.tab_orders.operation_in_progress:
                self.statusBar().showMessage(
                    tr(
                        "Critical update ready. Finish the current order operation; Luma will require the update when safe.",
                        self.language,
                    ),
                    30000,
                )
            else:
                self._enforce_mandatory_update()
            event.ignore()
            return
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
    apply_dark_palette(app)
    window = LumaMainWindow()
    window.show()
    sys.exit(app.exec())
