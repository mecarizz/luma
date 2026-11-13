"""Unit tests for the modernized main window navigation, pages, and shortcuts."""
import unittest
from PySide6.QtWidgets import QApplication

from ui_main import LumaMainWindow


class TestNavigationAndShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = LumaMainWindow()

    def tearDown(self):
        self.window.close()

    def test_navigation_across_all_pages(self):
        self.assertEqual(len(self.window._pages), 7)
        self.assertEqual(self.window.tabs.count(), 7)

        expected_titles = [
            "Overview",
            "Orders & Labels",
            "Seller Config",
            "Product Catalog",
            "Reports",
            "Activity Logs",
            "Settings",
        ]

        for i, expected_title in enumerate(expected_titles):
            self.window.navigate(i)
            self.assertEqual(self.window.tabs.currentIndex(), i)
            self.assertTrue(self.window.nav_buttons[i].isChecked())

    def test_language_switching_updates_all_nav_buttons(self):
        self.window.set_language("tr")
        self.assertIn("Genel Bakış", self.window.nav_buttons[0].text())
        self.assertIn("Siparişler", self.window.nav_buttons[1].text())
        self.assertIn("Satıcı", self.window.nav_buttons[2].text())
        self.assertIn("Kataloğu", self.window.nav_buttons[3].text())
        self.assertIn("Raporlar", self.window.nav_buttons[4].text())
        self.assertIn("Sistem Kayıtları", self.window.nav_buttons[5].text())
        self.assertIn("Ayarlar", self.window.nav_buttons[6].text())

        self.window.set_language("en")
        self.assertIn("Overview", self.window.nav_buttons[0].text())

    def test_monitoring_state_visual_indicators(self):
        self.window.set_monitoring_state(True)
        self.assertIn("ACTIVE", self.window.status_pill_badge.text())

        self.window.set_monitoring_state(False)
        self.assertIn("OFFLINE", self.window.status_pill_badge.text())


if __name__ == "__main__":
    unittest.main()
