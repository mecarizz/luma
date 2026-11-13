import sys
from functools import partial
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QTimer, Signal, Qt
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
)

from core.paths import is_frozen
from core.i18n import ask_yes_no, tr
from core.updates import (
    UpdateRelease,
    download_update,
    get_latest_release,
    install_update,
    launch_update,
)
from core.version import VERSION
from ui_dashboard import DashboardTab
from ui_sellers import SellersTab
from ui_catalog import CatalogTab
from ui_logs import LogsTab
from ui_orders import OrdersTab
from app_controller import AppController
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
        self.setMinimumSize(1050, 700)
        self.setStyleSheet(DARK_STYLESHEET)

        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(224)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(16, 24, 16, 18)
        side.setSpacing(8)

        brand_row = QHBoxLayout()
        mark = QLabel("◈")
        mark.setObjectName("brandMark")
        brand = QLabel("Luma")
        brand.setObjectName("brand")
        brand_row.addWidget(mark)
        brand_row.addWidget(brand)
        brand_row.addStretch()
        side.addLayout(brand_row)
        self.tagline = QLabel()
        self.tagline.setObjectName("muted")
        self.tagline.setStyleSheet("font-size: 7pt; letter-spacing: 1px;")
        side.addWidget(self.tagline)
        side.addSpacing(28)

        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self.tab_dashboard = DashboardTab()
        self.tab_sellers = SellersTab()
        self.tab_orders = OrdersTab()
        self.tab_catalog = CatalogTab()
        self.tab_logs = LogsTab()
        self._pages = [
            ("⌂", "Dashboard", self.tab_dashboard),
            ("▣", "Orders & Labels", self.tab_orders),
            ("♙", "Seller Config", self.tab_sellers),
            ("▦", "Product Catalog", self.tab_catalog),
            ("▤", "System Logs", self.tab_logs),
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

        health = QFrame()
        health.setObjectName("panel")
        health_layout = QVBoxLayout(health)
        health_layout.setContentsMargins(12, 12, 12, 12)
        self.health_title = QLabel()
        self.health_title.setObjectName("accent")
        self.health_note = QLabel("Luma services")
        self.health_note.setObjectName("muted")
        health_layout.addWidget(self.health_title)
        health_layout.addWidget(self.health_note)
        side.addWidget(health)
        version_label = QLabel(f"Version {VERSION}")
        version_label.setObjectName("muted")
        side.addWidget(version_label)
        shell.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 22, 28, 20)
        content_layout.setSpacing(16)
        top = QHBoxLayout()
        self.page_heading = QLabel()
        self.page_heading.setObjectName("pageTitle")
        top.addWidget(self.page_heading)
        top.addStretch()
        self.monitoring_label = QLabel()
        self.monitoring_label.setObjectName("accent")
        top.addWidget(self.monitoring_label)
        content_layout.addLayout(top)
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self.tabs)
        shell.addWidget(content, 1)

        self._release_check_worker = None
        self._update_download_worker = None
        self._release_check_silent = False
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
        self.set_language(self.language)
        self.navigate(0)

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
        # afterward so the catalog UI sees products.json copied from legacy installs.
        self.tab_catalog.refresh()
        QTimer.singleShot(1200, self.check_for_updates_on_startup)

    def navigate(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        title = self._pages[index][1]
        self.page_heading.setText(tr(title, self.language))

    def set_monitoring_state(self, active: bool) -> None:
        self.health_title.setText(
            tr("SYSTEM READY" if active else "SYSTEM UNAVAILABLE", self.language)
        )
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
        titles = (
            "Dashboard",
            "Orders & Labels",
            "Seller Config",
            "Product Catalog",
            "System Logs",
        )
        for index, title in enumerate(titles):
            self.tabs.setTabText(index, tr(title, language))
            self.nav_buttons[index].setText(
                f"{self._pages[index][0]}   {tr(title, language)}"
            )

        self.page_heading.setText(
            tr(titles[self.tabs.currentIndex()], language)
        )
        self.tab_dashboard.set_language(language)
        self.tab_orders.set_language(language)
        self.tab_sellers.set_language(language)
        self.tab_catalog.set_language(language)
        self.language_menu.setTitle(tr("Language", language))
        self.help_menu.setTitle(tr("Help", language))
        self.update_action.setText(tr("Check for Updates", language))
        self.tagline.setText(tr("MANAGE  ·  AUTOMATE  ·  GROW", language))
        self.health_note.setText(tr("Luma services", language))
        self.set_monitoring_state(
            self.controller is not None if hasattr(self, "controller") else False
        )
        for code, action in self.language_actions.items():
            action.setChecked(code == language)

    def closeEvent(self, event):
        if not self.tab_orders.stop_worker():
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