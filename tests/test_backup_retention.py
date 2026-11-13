"""Tests for automated backup retention and safe recovery from backup."""
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from core.catalog import ProductCatalog, ProductItem
from core.paths import find_latest_backup, prune_backups
from core.seller_manager import SellerManager
from core.seller_models import SellerProfile


class TestBackupRetention(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.backup_dir = Path(self.test_dir) / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_prune_backups_retains_latest_n(self):
        # Create 35 dummy backup files with staggered timestamps
        for i in range(35):
            backup_file = self.backup_dir / f"products_{20261100 + i}.json"
            backup_file.write_text("{}", encoding="utf-8")
            # stagger mtimes slightly
            os.utime(backup_file, (1000 + i * 10, 1000 + i * 10))

        initial_count = len(list(self.backup_dir.glob("products_*.json")))
        self.assertEqual(initial_count, 35)

        removed = prune_backups(self.backup_dir, "products_", keep=30)
        self.assertEqual(len(removed), 5)

        remaining = sorted(list(self.backup_dir.glob("products_*.json")))
        self.assertEqual(len(remaining), 30)

        # Ensure the remaining are the most recent ones (20261105 to 20261134)
        for old in range(5):
            self.assertFalse((self.backup_dir / f"products_{20261100 + old}.json").exists())
        self.assertTrue((self.backup_dir / "products_20261134.json").exists())

    def test_find_latest_backup(self):
        for i in range(3):
            f = self.backup_dir / f"sellers_{i}.json"
            f.write_text('{"sellers": []}', encoding="utf-8")
            os.utime(f, (2000 + i * 10, 2000 + i * 10))

        latest = find_latest_backup(self.backup_dir, "sellers_")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.name, "sellers_2.json")

    def test_catalog_recovers_from_backup_on_corruption(self):
        cat_file = os.path.join(self.test_dir, "products.json")
        catalog = ProductCatalog(cat_file)
        catalog.add_or_update(ProductItem(barcode="BC101", display_name="Item 101"))
        catalog.save()

        # Corrupt the primary catalog file
        with open(cat_file, "w", encoding="utf-8") as f:
            f.write("{ INVALID CORRUPTED JSON !!!")

        # Reloading catalog should recover from backup
        recovered_catalog = ProductCatalog(cat_file)
        item = recovered_catalog.get_by_barcode("BC101")
        self.assertIsNotNone(item)
        self.assertEqual(item.display_name, "Item 101")

    def test_seller_manager_recovers_from_backup_on_corruption(self):
        seller_file = os.path.join(self.test_dir, "sellers.json")
        sm = SellerManager(seller_file)
        profile = SellerProfile(
            seller_id="999888",
            name="Store 999",
            api_key="key",
            api_secret="sec",
        )
        sm.save_profile(profile)
        # Call save_profile again to trigger backup of existing sellers.json
        profile.name = "Store 999 Updated"
        sm.save_profile(profile)

        # Corrupt primary sellers file
        with open(seller_file, "w", encoding="utf-8") as f:
            f.write("{ INVALID JSON !!!")

        # Reloading SellerManager should recover from latest backup
        recovered_sm = SellerManager(seller_file)
        recovered_profile = recovered_sm.get("999888")
        self.assertIsNotNone(recovered_profile)
        self.assertTrue("Store 999" in recovered_profile.name)


if __name__ == "__main__":
    unittest.main()
