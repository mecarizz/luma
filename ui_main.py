import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.paths import is_frozen
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
        self.setWindowTitle("Luma Multi-Seller Manager")
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
        update_action = self.menuBar().addMenu("Help").addAction("Check for Updates")
        update_action.triggered.connect(self.check_for_updates)

        self.controller = None
        try:
            self.controller = AppController(self)
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Seller configuration error",
                f"The seller configuration could not be loaded. Watching is disabled.\n\n{exc}",
            )
            self.tab_sellers.setEnabled(False)

    def check_for_updates(self):
        if not is_frozen():
            QMessageBox.information(
                self,
                "Check for updates",
                "Update installation is available in the packaged Windows application.",
            )
            return

        self.menuBar().setEnabled(False)
        self._release_check_worker = _ReleaseCheckWorker(self)
        self._release_check_worker.completed.connect(self._on_release_checked)
        self._release_check_worker.failed.connect(self._on_update_failed)
        self._release_check_worker.finished.connect(self._on_release_check_finished)
        self._release_check_worker.start()

    def _on_release_check_finished(self):
        self._release_check_worker = None
        if self._update_download_worker is None:
            self.menuBar().setEnabled(True)

    def _on_release_checked(self, release):
        if release is None:
            QMessageBox.information(self, "Check for updates", f"Luma is up to date (v{VERSION}).")
            return

        notes = release.notes.strip()[:3000] or "No release notes were provided."
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Luma update available")
        prompt.setText(f"{release.title}\nVersion {release.version} is available (current: {VERSION}).")
        prompt.setInformativeText(f"{notes}\n\nDownload and install this update?")
        prompt.setTextFormat(Qt.PlainText)
        prompt.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        prompt.setDefaultButton(QMessageBox.No)
        if prompt.exec() != QMessageBox.Yes:
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
        answer = QMessageBox.question(
            self,
            "Update ready",
            "The update passed its SHA-256 check and is ready to install. Restart Luma now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            QMessageBox.information(
                self,
                "Update downloaded",
                f"The verified update is staged at:\n{Path(staged_path)}\nRestart the app to install it later.",
            )
            return

        try:
            launch_update(Path(staged_path))
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Update failed", f"Could not start the updater:\n{exc}")
            return
        QApplication.quit()

    def _on_update_failed(self, message):
        QMessageBox.warning(self, "Update check failed", message)

    def closeEvent(self, event):
        if not self.tab_orders.stop_worker():
            QMessageBox.information(
                self,
                "Operation in progress",
                "The order operation is still running. Please wait for it to finish before closing Luma.",
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