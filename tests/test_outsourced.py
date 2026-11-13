"""Tests for the Outsourced Products catalog section and order notification dialog."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Qt application must be created before importing any Qt widgets
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)


class TestOutsourcedCatalogSection(unittest.TestCase):
    """Unit tests for the Outsourced tab inside CatalogTab."""

    def setUp(self):
        import shutil
        self.tmp = tempfile.mkdtemp()
        self.products_file = os.path.join(self.tmp, "products.json")
        self.outsourced_file = os.path.join(self.tmp, "outsourced_products.txt")
        # Create empty products file
        with open(self.products_file, "w", encoding="utf-8") as f:
            f.write('{"products": {}}')
        # Empty outsourced rules
        open(self.outsourced_file, "w").close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_tab(self):
        from ui_catalog import CatalogTab
        with (
            patch("ui_catalog.get_config") as mock_cfg,
            patch("ui_catalog.get_data_path") as mock_dp,
        ):
            mock_cfg.return_value.products_file = self.products_file
            mock_dp.return_value = self.outsourced_file
            tab = CatalogTab()
        return tab

    def test_catalog_tab_initializes_with_two_subpages(self):
        """CatalogTab should expose a QStackedWidget with Master and Outsourced pages."""
        tab = self._make_tab()
        self.assertEqual(tab.stack.count(), 2)

    def test_outsourced_subpage_has_rule_input(self):
        tab = self._make_tab()
        # The add-rule input field should exist and accept text
        tab.input_new_rule.setText("TEST123")
        self.assertEqual(tab.input_new_rule.text(), "TEST123")

    def test_add_and_remove_outsourced_rule(self):
        tab = self._make_tab()
        # Add a pattern directly via the classifier
        tab.classifier.add_pattern("AYKK*")
        tab.refresh_rules()
        self.assertEqual(tab.rules_table.rowCount(), 1)
        self.assertEqual(tab.rules_table.item(0, 0).text(), "AYKK*")

        # Remove it
        tab.rules_table.selectRow(0)
        tab.classifier.remove_pattern("AYKK*")
        tab.refresh_rules()
        self.assertEqual(tab.rules_table.rowCount(), 0)

    def test_barcode_tester_reports_outsourced_match(self):
        tab = self._make_tab()
        tab.classifier.add_pattern("AYKK*")
        tab.input_test_barcode.setText("AYKK1234")
        tab.test_barcode_match()
        self.assertIn("AYKK*", tab.lbl_test_result.text())
        self.assertIn("OUTSOURCED", tab.lbl_test_result.text().upper())

    def test_barcode_tester_reports_in_house_for_unmatched(self):
        tab = self._make_tab()
        tab.input_test_barcode.setText("XYZ9999")
        tab.test_barcode_match()
        self.assertIn("IN-HOUSE", tab.lbl_test_result.text().upper())

    def test_switch_to_outsourced_subpage(self):
        tab = self._make_tab()
        tab._set_subpage(1)
        self.assertEqual(tab.stack.currentIndex(), 1)
        tab._set_subpage(0)
        self.assertEqual(tab.stack.currentIndex(), 0)

    def test_validate_rules_detects_no_issues_on_clean_list(self):
        tab = self._make_tab()
        tab.classifier.add_pattern("AABB1234")
        report = tab.classifier.load(force=True)
        self.assertEqual(report.duplicates, [])
        self.assertEqual(report.redundant_rules, [])


class TestOutsourcedOrderNotificationDialog(unittest.TestCase):
    """Unit tests for the notification dialog shown when outsourced orders are selected."""

    def _make_dialog(self, kind="outsourced"):
        from core.classifier import ClassificationResult
        from ui_orders import OutsourcedOrderNotificationDialog

        pkg = {
            "orderNumber": "98765",
            "shipmentPackageId": "11111",
            "shipmentAddress": {"fullName": "Ahmet Yılmaz"},
            "lines": [{"barcode": "AYKK0001", "quantity": 1}],
        }
        res = ClassificationResult(
            kind=kind,
            do_print=False,
            do_save=True,
            matched_lines=pkg["lines"],
            matched_rules={"AYKK*"},
        )
        return OutsourcedOrderNotificationDialog(
            parent=None,
            outsourced_items=[(pkg, res)],
            target_cargo="DHLECOMMP",
            language="en",
        )

    def test_dialog_shows_correct_order_count(self):
        dlg = self._make_dialog()
        # The dialog should show 1 affected order in the table
        # Find the table inside the dialog
        from PySide6.QtWidgets import QTableWidget
        tables = dlg.findChildren(QTableWidget)
        self.assertTrue(len(tables) >= 1)
        affected_table = tables[0]
        self.assertEqual(affected_table.rowCount(), 1)

    def test_dialog_save_pdf_action(self):
        dlg = self._make_dialog()
        from ui_orders import OutsourcedOrderNotificationDialog
        dlg.btn_save_pdf.click()
        self.assertEqual(dlg.selected_action, OutsourcedOrderNotificationDialog.ACTION_SAVE_PDF)

    def test_dialog_print_anyway_action(self):
        dlg = self._make_dialog()
        from ui_orders import OutsourcedOrderNotificationDialog
        dlg.btn_print_anyway.click()
        self.assertEqual(dlg.selected_action, OutsourcedOrderNotificationDialog.ACTION_PRINT_ANYWAY)

    def test_dialog_cancel_action(self):
        dlg = self._make_dialog()
        from ui_orders import OutsourcedOrderNotificationDialog
        dlg.btn_cancel.click()
        self.assertEqual(dlg.selected_action, OutsourcedOrderNotificationDialog.ACTION_CANCEL)

    def test_dialog_works_with_mixed_kind(self):
        dlg = self._make_dialog(kind="mixed")
        from PySide6.QtWidgets import QTableWidget
        tables = dlg.findChildren(QTableWidget)
        self.assertEqual(tables[0].rowCount(), 1)


class TestOrdersTabOutsourcedRouting(unittest.TestCase):
    """Integration tests for outsourced routing in OrdersTab.print_selected."""

    def _make_orders_tab(self):
        from ui_orders import OrdersTab
        with patch("ui_orders.get_data_path") as mock_dp:
            mock_dp.return_value = "/nonexistent/outsourced_products.txt"
            tab = OrdersTab()
        return tab

    def test_print_selected_aborts_when_no_packages_selected(self):
        tab = self._make_orders_tab()
        # No packages loaded — should show info dialog, not crash
        shown = []
        with patch("ui_orders.QMessageBox.information", side_effect=lambda *a, **kw: shown.append(True)):
            tab.print_selected("DHLECOMMP")
        self.assertTrue(shown, "Should have shown 'select at least one' message")

    def test_classifier_loaded_on_init(self):
        tab = self._make_orders_tab()
        # Classifier must be initialized even if file doesn't exist
        from core.classifier import OutsourcedClassifier
        self.assertIsInstance(tab._classifier, OutsourcedClassifier)


if __name__ == "__main__":
    unittest.main()
