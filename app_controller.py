"""Connect seller profile persistence, the UI, and the Trendyol watcher."""
from core.logger import setup_logger
from core.seller_manager import SellerManager
from core.paths import get_data_dir, initialize_runtime_data, is_frozen
from worker import SellerWorker


class AppController:
    def __init__(self, main_window):
        self.ui = main_window
        logger = setup_logger()
        logger.info(
            "Luma startup: frozen=%s data_dir=%s",
            is_frozen(),
            get_data_dir(),
        )
        try:
            initialize_runtime_data()
            self.seller_manager = SellerManager()
        except Exception:
            logger.exception("Luma could not initialize runtime data or load seller profiles")
            raise
        self.worker = None
        logger.info(
            "Seller profiles loaded: total=%d active_monitoring=%d",
            len(self.seller_manager.list_all()),
            sum(
                profile.is_active and profile.monitoring_enabled
                for profile in self.seller_manager.list_all()
            ),
        )

        self.ui.tab_sellers.set_manager(self.seller_manager)
        self.ui.tab_orders.set_manager(self.seller_manager)
        self.ui.tab_orders.log_emitted.connect(self.ui.tab_logs.append_log)
        self.ui.tab_orders.operation_started.connect(self.pause_watcher)
        self.ui.tab_orders.operation_finished.connect(self.resume_watcher)
        self.ui.tab_sellers.seller_configuration_changed.connect(self.refresh_workers)
        self.load_and_start_workers()

    def load_and_start_workers(self):
        self.start_watcher()

    def start_watcher(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.worker = SellerWorker(self.seller_manager.list_all())
        self.worker.log_emitted.connect(self.ui.tab_logs.append_log)
        self.worker.order_processed.connect(self.ui.tab_dashboard.add_order_row)
        self.worker.status_updated.connect(self._update_seller_status)
        self.worker.start()
        self._update_active_seller_count()

    def pause_watcher(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        self.worker = None

    def resume_watcher(self):
        self.start_watcher()

    def refresh_workers(self):
        if self.worker is not None:
            self.worker.set_profiles(self.seller_manager.list_all())
        self.ui.tab_orders.refresh_sellers()
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
        self.pause_watcher()
