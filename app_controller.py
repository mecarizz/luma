"""Connect seller profile persistence, the UI, and the Trendyol watcher."""
from core.seller_manager import SellerManager
from core.paths import initialize_runtime_data
from worker import SellerWorker


class AppController:
    def __init__(self, main_window):
        self.ui = main_window
        initialize_runtime_data()
        self.seller_manager = SellerManager()
        self.worker = None

        self.ui.tab_sellers.set_manager(self.seller_manager)
        self.ui.tab_sellers.seller_configuration_changed.connect(self.refresh_workers)
        self.load_and_start_workers()

    def load_and_start_workers(self):
        self.worker = SellerWorker(self.seller_manager.list_all())
        self.worker.log_emitted.connect(self.ui.tab_logs.append_log)
        self.worker.order_processed.connect(self.ui.tab_dashboard.add_order_row)
        self.worker.status_updated.connect(self._update_seller_status)
        self.worker.start()
        self._update_active_seller_count()

    def refresh_workers(self):
        if self.worker is not None:
            self.worker.set_profiles(self.seller_manager.list_all())
        self._update_active_seller_count()

    def _update_active_seller_count(self):
        active = sum(
            profile.is_active and profile.monitoring_enabled
            for profile in self.seller_manager.list_all()
        )
        self.ui.tab_dashboard.card_active_sellers.lbl_value.setText(str(active))

    def _update_seller_status(self, seller_id, status):
        self.ui.tab_sellers.set_seller_status(seller_id, status)

    def stop_all_workers(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
