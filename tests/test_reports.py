"""Unit tests for the ReportingEngine."""
import csv
import json
import os
import shutil
import tempfile
import unittest
from core.reporting import ReportingEngine


class TestReporting(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.test_dir, "printed_packages.json")
        self.unknown_file = os.path.join(self.test_dir, "unknown_products.json")

        sample_state = {
            "packages": {
                "3330000001": {
                    "orderNumber": "10001",
                    "seller": "674974",
                    "carrier": "DHL eCommerce",
                    "kind": "normal",
                    "action": "printed",
                    "at": "2026-11-10T10:00:00",
                },
                "3330000002": {
                    "orderNumber": "10002",
                    "seller": "674974",
                    "carrier": "DHL eCommerce",
                    "kind": "outsourced",
                    "action": "outsourced",
                    "pdf": "outsourced_labels/test.pdf",
                    "at": "2026-11-10T11:00:00",
                },
                "3330000003": {
                    "orderNumber": "10003",
                    "seller": "1234567",
                    "carrier": "DHL eCommerce",
                    "kind": "mixed",
                    "action": "printed+saved",
                    "pdf": "outsourced_labels/test_mixed.pdf",
                    "at": "2026-11-09T15:00:00",
                },
                "3330000004": {
                    "orderNumber": "10004",
                    "seller": "1234567",
                    "carrier": "Yurtiçi",
                    "kind": "normal",
                    "action": "switch_failed",
                    "at": "2026-11-09T16:00:00",
                },
                "3330000005": {
                    "orderNumber": "10005",
                    "seller": "674974",
                    "action": "baseline",
                    "at": "2026-11-08T09:00:00",
                },
            }
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(sample_state, f)

        with open(self.unknown_file, "w", encoding="utf-8") as f:
            json.dump({"UNMAPPED1": {}, "UNMAPPED2": {}}, f)

        self.engine = ReportingEngine(self.state_file, self.unknown_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_summary_aggregation(self):
        stats = self.engine.get_summary()
        self.assertEqual(stats.total_packages, 5)
        self.assertEqual(stats.printed_count, 2)  # 3330000001 and 3330000003
        self.assertEqual(stats.outsourced_count, 1)  # 3330000002
        self.assertEqual(stats.mixed_count, 1)  # 3330000003
        self.assertEqual(stats.failed_count, 1)  # 3330000004
        self.assertEqual(stats.baseline_count, 1)  # 3330000005
        self.assertEqual(stats.unknown_products_count, 2)

    def test_seller_breakdown(self):
        stats = self.engine.get_summary()
        self.assertIn("674974", stats.by_seller)
        self.assertIn("1234567", stats.by_seller)
        self.assertEqual(stats.by_seller["674974"]["total"], 3)
        self.assertEqual(stats.by_seller["1234567"]["total"], 2)

    def test_daily_breakdown(self):
        stats = self.engine.get_summary()
        self.assertIn("2026-11-10", stats.by_day)
        self.assertIn("2026-11-09", stats.by_day)
        self.assertIn("2026-11-08", stats.by_day)
        self.assertEqual(stats.by_day["2026-11-10"]["total"], 2)

    def test_export_to_csv(self):
        out_csv = os.path.join(self.test_dir, "export.csv")
        count = self.engine.export_history_to_csv(out_csv)
        self.assertEqual(count, 5)

        with open(out_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 5)
            self.assertIn("package_id", rows[0])
            self.assertIn("order_number", rows[0])


if __name__ == "__main__":
    unittest.main()
