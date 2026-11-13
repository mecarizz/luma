"""Unit tests for modernized UI components, reporting, logs, and settings tabs."""
import os
import shutil
import tempfile
import unittest
from PySide6.QtWidgets import QApplication

from ui_components import EmptyStateWidget, MetricCard, SearchInput, SectionHeader, StatusBadge
from ui_dashboard import DashboardTab
from ui_logs import LogsTab
from ui_reports import ReportsTab
from ui_settings import SettingsTab


class TestModernUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_metric_card_value_and_language(self):
        card = MetricCard(title="Active Sellers", initial_value="5", subtitle="Connected stores")
        self.assertEqual(card.lbl_value.text(), "5")
        self.assertEqual(card.lbl_title.text(), "Active Sellers")

        card.set_value(12)
        self.assertEqual(card.lbl_value.text(), "12")

        card.set_language("tr")
        self.assertEqual(card.lbl_title.text(), "Aktif Satıcılar")

    def test_status_badge_variants(self):
        badge = StatusBadge("ACTIVE", "success")
        self.assertIn("#064e3b", badge.styleSheet())

        badge.set_variant("error")
        self.assertIn("#7f1d1d", badge.styleSheet())

        badge.set_variant("warning")
        self.assertIn("#78350f", badge.styleSheet())

    def test_empty_state_widget(self):
        called = []
        widget = EmptyStateWidget(
            title="No Items Found",
            description="Try adjusting your search criteria.",
            button_text="Reset Search",
            button_callback=lambda: called.append(True),
        )
        self.assertEqual(widget.lbl_title.text(), "No Items Found")
        self.assertIsNotNone(widget.action_btn)
        widget.action_btn.click()
        self.assertEqual(called, [True])

    def test_reports_tab_initialization_and_refresh(self):
        tab = ReportsTab()
        self.assertGreaterEqual(tab.tabs.count(), 3)
        tab.set_language("tr")
        self.assertEqual(tab.tabs.tabText(0), "Günlük Gönderim")
        self.assertEqual(tab.tabs.tabText(1), "Kargo Dağılımı")
        self.assertEqual(tab.tabs.tabText(2), "Satıcı Kırılımı")

    def test_logs_tab_filtering_and_severity(self):
        tab = LogsTab()
        tab._clear_view()
        tab._all_records.clear()

        tab.append_log("[2026-11-13 10:00:00] [INFO] Normal startup")
        tab.append_log("[2026-11-13 10:01:00] [WARNING] Rate limit threshold near")
        tab.append_log("[2026-11-13 10:02:00] [ERROR] Connection timeout occurred")

        self.assertEqual(len(tab._all_records), 3)

        # Filter by error severity
        idx = tab.level_combo.findData("ERROR")
        tab.level_combo.setCurrentIndex(idx)
        text = tab.log_viewer.toPlainText()
        self.assertIn("Connection timeout", text)
        self.assertNotIn("Normal startup", text)

    def test_settings_tab_localization(self):
        tab = SettingsTab()
        tab.set_language("en")
        self.assertEqual(tab.lbl_sec_general.text(), "General & Localization")

        tab.set_language("tr")
        self.assertEqual(tab.lbl_sec_general.text(), "Genel ve Dil")


if __name__ == "__main__":
    unittest.main()
