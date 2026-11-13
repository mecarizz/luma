import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QTimer, Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.paths import is_frozen
from core.i18n import ask_yes_no, tr
from core.updates import UpdateRelease, download_update, get_latest_release, launch_update
from core.version import VERSION
from ui_dashboard import DashboardTab
from ui_sellers import SellersTab
from ui_catalog import CatalogTab
from ui_logs import LogsTab
from ui_orders import OrdersTab
from app_controller import AppController


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
            self.completed.emit(download_update(self.release))
        except Exception as exc:
            self.failed.emit(str(exc))


class LumaMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Luma", "Luma")
        saved_language = self.settings.value("language", "en")
        self.language = saved_language if saved_language in ("en", "tr") else "en"
        self.resize(1024, 768)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget()
        
        self.tab_dashboard = DashboardTab()
        self.tab_sellers = SellersTab()
        self.tab_orders = OrdersTab()
        self.tab_catalog = CatalogTab()
        self.tab_logs = LogsTab()

        self.tabs.addTab(self.tab_dashboard, "Dashboard")
        self.tabs.addTab(self.tab_orders, "Orders & Labels")
        self.tabs.addTab(self.tab_sellers, "Seller Config")
        self.tabs.addTab(self.tab_catalog, "Product Catalog")
        self.tabs.addTab(self.tab_logs, "System Logs")

        layout.addWidget(self.tabs)

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

        self.controller = None
        try:
            self.controller = AppController(self)
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(
                self,
                tr("Seller configuration error", self.language),
                tr(
                    "The seller configuration could not be loaded. Watching is disabled.\n\n{error}",
                    self.language,
                ).format(error=exc),
            )
            self.tab_sellers.setEnabled(False)

        QTimer.singleShot(1200, self.check_for_updates_on_startup)

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

    def _on_update_downloaded(self, staged_path):
        answer = ask_yes_no(
            self,
            "Update ready",
            "The update passed its SHA-256 check and is ready to install. Restart Luma now?",
            self.language,
        )
        if not answer:
            QMessageBox.information(
                self,
                tr("Update downloaded", self.language),
                tr(
                    "The verified update is staged at:\n{path}\nRestart the app to install it later.",
                    self.language,
                ).format(path=Path(staged_path)),
            )
            return

        try:
            launch_update(Path(staged_path))
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

        self.tab_dashboard.set_language(language)
        self.tab_orders.set_language(language)
        self.tab_sellers.set_language(language)
        self.tab_catalog.set_language(language)
        self.language_menu.setTitle(tr("Language", language))
        self.help_menu.setTitle(tr("Help", language))
        self.update_action.setText(tr("Check for Updates", language))
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