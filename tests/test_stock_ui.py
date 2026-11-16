import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox, QSpinBox

from core.catalog import ProductItem
from core.seller_models import SellerProfile
from core.trendyol_inventory import InventoryProduct
from ui_stock import StockTab


class TestStockTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        catalog_patch = patch("ui_stock.ProductCatalog")
        self.addCleanup(catalog_patch.stop)
        catalog_type = catalog_patch.start()
        catalog_type.return_value.list_all.return_value = []
        self.tab = StockTab()
        self.addCleanup(self.tab.close)

    def _set_sellers(self, *seller_ids):
        manager = type(
            "SellerManagerStub",
            (),
            {"list_all": lambda _self: [SellerProfile(seller_id=sid) for sid in seller_ids]},
        )()
        self.tab.set_manager(manager)

    def test_quantity_change_is_marked_for_update(self):
        self._set_sellers("123456")
        self.tab._inventory = [
            InventoryProduct("BC-1", 5, "SKU-1", "Product one"),
            InventoryProduct("BC-2", 0, "SKU-2", "Product two"),
        ]
        self.tab._render_inventory()

        quantity_input = self.tab.inventory_table.cellWidget(0, 4)
        self.assertIsInstance(quantity_input, QSpinBox)
        quantity_input.setValue(8)

        self.assertEqual(
            self.tab._pending_changes(),
            [{"barcode": "BC-1", "quantity": 8}],
        )
        self.assertTrue(self.tab.apply_button.isEnabled())

    def test_live_product_title_is_visible(self):
        self.tab._inventory = [
            InventoryProduct("BC-1", 5, "SKU-1", "Live product title"),
        ]
        self.tab._render_inventory()

        self.assertEqual(self.tab.inventory_table.item(0, 1).text(), "Live product title")

    def test_catalog_title_can_match_by_seller_sku(self):
        profile = SellerProfile(
            seller_id="123456",
            name="Test Seller",
        )
        manager = type(
            "SellerManagerStub",
            (),
            {"list_all": lambda _self: [profile]},
        )()
        self.tab.set_manager(manager)
        self.tab.catalog.list_all.return_value = [
            ProductItem(
                barcode="OTHER-BC",
                display_name="Catalog product title",
                stock_code="SKU-1",
                seller="Test Seller",
            )
        ]
        self.tab._inventory = [
            InventoryProduct("BC-1", 5, "SKU-1", ""),
        ]
        self.tab._render_inventory()

        self.assertEqual(
            self.tab.inventory_table.item(0, 1).text(),
            "Catalog product title",
        )

    def test_unknown_live_quantity_cannot_be_changed(self):
        self._set_sellers("123456")
        self.tab._inventory = [
            InventoryProduct("BC-1", None, "SKU-1", "Product one"),
        ]
        self.tab._render_inventory()

        quantity_input = self.tab.inventory_table.cellWidget(0, 4)
        self.assertFalse(quantity_input.isEnabled())
        self.assertEqual(self.tab._pending_changes(), [])
        self.assertFalse(self.tab.apply_button.isEnabled())

    def test_changing_seller_clears_previous_seller_inventory(self):
        self._set_sellers("123456", "654321")
        self.tab._inventory = [
            InventoryProduct("BC-1", 5, "SKU-1", "Product one"),
        ]
        self.tab._render_inventory()

        self.tab.seller_combo.setCurrentIndex(1)

        self.assertEqual(self.tab._inventory, [])
        self.assertEqual(self.tab.inventory_table.rowCount(), 0)
        self.assertFalse(self.tab.apply_button.isEnabled())

    def test_cancel_confirmation_does_not_start_update(self):
        self._set_sellers("123456")
        self.tab._inventory = [
            InventoryProduct("BC-1", 5, "SKU-1", "Product one"),
        ]
        self.tab._render_inventory()
        self.tab.inventory_table.cellWidget(0, 4).setValue(8)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            with patch.object(self.tab, "_start_worker") as start_worker:
                self.tab.apply_changes()

        start_worker.assert_not_called()

    def test_uncertain_update_blocks_retry_until_inventory_is_refreshed(self):
        self._set_sellers("123456")
        self.tab._inventory = [
            InventoryProduct("BC-1", 5, "SKU-1", "Product one"),
        ]
        self.tab._render_inventory()
        self.tab.inventory_table.cellWidget(0, 4).setValue(8)

        with patch.object(QMessageBox, "critical"):
            self.tab._on_worker_failed("update", "request timed out")
        self.tab._on_worker_finished()

        self.assertTrue(self.tab._pending_result)
        self.assertFalse(self.tab.apply_button.isEnabled())
        with patch.object(QMessageBox, "question") as question:
            with patch.object(self.tab, "_start_worker") as start_worker:
                self.tab.apply_changes()

        question.assert_not_called()
        start_worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
