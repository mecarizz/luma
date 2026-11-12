"""Unit tests for the Product Catalog, resolution priority, and unknown tracker."""
import json
import os
import shutil
import tempfile
import unittest
from core.catalog import (
    ProductCatalog,
    ProductItem,
    WildcardRule,
    normalize_identifier,
)
from core.unknown_tracker import UnknownProductTracker


class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_barcode_normalization(self):
        self.assertEqual(normalize_identifier(" lhlpk "), "LHLPK")
        self.assertEqual(normalize_identifier("lhlp-001"), "LHLP-001")
        self.assertEqual(normalize_identifier("ipek"), "İPEK")
        self.assertEqual(normalize_identifier("ılık"), "ILIK")
        self.assertEqual(normalize_identifier(None), "")

    def test_catalog_exact_barcode_match(self):
        cat_file = os.path.join(self.test_dir, "test_products.json")
        catalog = ProductCatalog(cat_file)

        item = ProductItem(
            barcode="LHLPK",
            display_name="LORIA ÇİFT EKRU",
            stock_code="PE",
            seller="Loria",
            size_type="ÇİFT",
        )
        catalog.add_or_update(item)

        found = catalog.get_by_barcode("LHLPK")
        self.assertIsNotNone(found)
        self.assertEqual(found.display_name, "LORIA ÇİFT EKRU")
        self.assertEqual(found.size_type, "ÇİFT")

        found_lower = catalog.get_by_barcode("lhlpk")
        self.assertIsNotNone(found_lower)
        self.assertEqual(found_lower.display_name, "LORIA ÇİFT EKRU")

    def test_catalog_stock_code_fallback(self):
        cat_file = os.path.join(self.test_dir, "test_products.json")
        catalog = ProductCatalog(cat_file)

        item = ProductItem(
            barcode="LHLPK",
            display_name="LORIA ÇİFT EKRU",
            stock_code="PE",
            seller="Loria",
            size_type="ÇİFT",
        )
        catalog.add_or_update(item)

        name, stype, src = catalog.resolve(
            barcode="UNKNOWN_BC",
            stock_code="PE",
            product_name="Some other title",
        )
        self.assertEqual(name, "LORIA ÇİFT EKRU")
        self.assertEqual(stype, "ÇİFT")
        self.assertEqual(src, "catalog_stock_code")

    def test_catalog_wildcard_matching(self):
        cat_file = os.path.join(self.test_dir, "test_products.json")
        catalog = ProductCatalog(cat_file)

        catalog._wildcards.append(
            WildcardRule(
                pattern="AYKK*",
                display_name="AYLA KIRLENT SERİSİ",
                seller="Ayla Home",
                size_type=None,
            )
        )
        catalog.save()

        name, stype, src = catalog.resolve(
            barcode="AYKK99_SPECIAL",
            stock_code="UNKNOWN",
            product_name="Ayla Kadife Kırlent",
        )
        self.assertEqual(name, "AYLA KIRLENT SERİSİ")
        self.assertEqual(src, "catalog_wildcard")

    def test_deterministic_priority_resolution(self):
        cat_file = os.path.join(self.test_dir, "test_products.json")
        catalog = ProductCatalog(cat_file)

        catalog.add_or_update(
            ProductItem(
                barcode="BC_EXACT",
                display_name="EXACT CATALOG NAME",
                stock_code="STK_EXACT",
            )
        )

        catalog._wildcards.append(
            WildcardRule(pattern="BC_*", display_name="WILDCARD NAME")
        )
        catalog.save()

        overrides = {"BC_EXACT": "OVERRIDE NAME", "BC_OTHER": "OVERRIDE OTHER"}

        # Exact barcode must beat overrides and wildcards
        name, _, src = catalog.resolve(
            barcode="BC_EXACT",
            stock_code="STK_EXACT",
            product_name="Trendyol Raw Title",
            overrides=overrides,
        )
        self.assertEqual(name, "EXACT CATALOG NAME")
        self.assertEqual(src, "catalog_barcode")

        # Override beats Trendyol fallback when barcode is not in catalog
        name2, _, src2 = catalog.resolve(
            barcode="NON_CATALOG_BC",
            stock_code="BC_OTHER",
            product_name="Trendyol Raw Title",
            overrides=overrides,
        )
        self.assertEqual(name2, "OVERRIDE OTHER")
        self.assertEqual(src2, "manual_override")

        # Trendyol fallback when nothing matches
        name3, _, src3 = catalog.resolve(
            barcode="UNKNOWN_123",
            stock_code="UNKNOWN_STK",
            product_name="Loria Peluş Çift Kişilik",
            overrides={},
            name_words=1,
        )
        self.assertEqual(name3, "LORIA")
        self.assertEqual(src3, "trendyol_fallback")

    def test_unknown_product_tracking(self):
        unk_file = os.path.join(self.test_dir, "test_unknown.json")
        tracker = UnknownProductTracker(unk_file)

        entry = tracker.record_unknown(
            barcode="NEW_BARCODE_1",
            stock_code="STK_01",
            trendyol_name="Yeni Ürün Test",
            seller_name="Loria",
            order_number="10001",
        )
        self.assertEqual(entry.occurrence_count, 1)
        self.assertEqual(entry.barcode, "NEW_BARCODE_1")

        entry2 = tracker.record_unknown(
            barcode="new_barcode_1",
            order_number="10002",
        )
        self.assertEqual(entry2.occurrence_count, 2)

        tracker_reloaded = UnknownProductTracker(unk_file)
        all_entries = tracker_reloaded.list_all()
        self.assertEqual(len(all_entries), 1)
        self.assertEqual(all_entries[0].occurrence_count, 2)

        tracker_reloaded.remove("NEW_BARCODE_1")
        self.assertEqual(len(tracker_reloaded.list_all()), 0)

    def test_catalog_backup_on_save(self):
        cat_file = os.path.join(self.test_dir, "products.json")
        catalog = ProductCatalog(cat_file)

        catalog.add_or_update(
            ProductItem(barcode="TEST1", display_name="Test Product 1")
        )
        catalog.add_or_update(
            ProductItem(barcode="TEST1", display_name="Test Product 1 Updated")
        )

        backup_dir = os.path.join(self.test_dir, "backups")
        self.assertTrue(os.path.exists(backup_dir))
        backups = [f for f in os.listdir(backup_dir) if f.startswith("products_")]
        self.assertGreaterEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main()
