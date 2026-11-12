"""Unit tests for watcher state management, DHL switching, and refetch identity validation."""
import json
import os
import shutil
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import trendyol_watcher as tw


class TestWatcher(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_refetch_as_dhl_strict_id_matching(self):
        """Verify that refetch_as_dhl NEVER accepts a different package with matching orderNumber."""
        target_pkg = {
            "orderNumber": "1001",
            "shipmentPackageId": 999111,
            "cargoProviderName": "Yurtiçi Kargo",
        }
        other_pkg = {
            "orderNumber": "1001",
            "shipmentPackageId": 999222,  # Different package ID from same order!
            "cargoProviderName": "DHL eCommerce Marketplace",
        }

        with patch.object(tw.tl, "fetch_packages", return_value=[other_pkg]):
            with patch.object(tw.time, "sleep", return_value=None):
                opts = SimpleNamespace(status=["Picking"])
                result = tw.refetch_as_dhl(target_pkg, opts, tries=2)
                # Must be None! Must NOT return other_pkg!
                self.assertIsNone(result)

    def test_refetch_as_dhl_success_on_match(self):
        target_pkg = {
            "orderNumber": "1001",
            "shipmentPackageId": 999111,
            "cargoProviderName": "Yurtiçi Kargo",
        }
        dhl_updated_pkg = {
            "orderNumber": "1001",
            "shipmentPackageId": 999111,  # Exact matching package ID!
            "cargoProviderName": "DHL eCommerce Marketplace",
            "cargoTrackingNumber": 7280038706106453,
        }

        with patch.object(tw.tl, "fetch_packages", return_value=[dhl_updated_pkg]):
            with patch.object(tw.time, "sleep", return_value=None):
                opts = SimpleNamespace(status=["Picking"])
                result = tw.refetch_as_dhl(target_pkg, opts, tries=2)
                self.assertIsNotNone(result)
                self.assertEqual(result["shipmentPackageId"], 999111)
                self.assertEqual(result["cargoTrackingNumber"], 7280038706106453)

    def test_persistent_state_atomic_save_and_recovery(self):
        state_file = os.path.join(self.test_dir, "printed_packages.json")
        with patch.object(tw, "STATE_FILE", state_file):
            state = tw.load_state()
            self.assertEqual(state, {"packages": {}, "sellers_seen": [], "in_progress": {}})

            # Record a package waiting for retry
            state["in_progress"]["333001"] = {
                "orderNumber": "10001",
                "retry_at": time.time() + 300,
                "switch_attempts": 1,
                "saved_pdf": "outsourced_labels/test.pdf",
            }
            tw.save_state(state)

            self.assertTrue(os.path.exists(state_file))
            reloaded = tw.load_state()
            self.assertIn("333001", reloaded["in_progress"])
            self.assertEqual(reloaded["in_progress"]["333001"]["switch_attempts"], 1)
            self.assertEqual(reloaded["in_progress"]["333001"]["saved_pdf"], "outsourced_labels/test.pdf")

    def test_baseline_marking(self):
        state_file = os.path.join(self.test_dir, "printed_packages.json")
        with patch.object(tw, "STATE_FILE", state_file):
            state = tw.load_state()
            seller = {"id": "674974", "key": "k", "secret": "s", "name": "Loria"}
            opts = SimpleNamespace(
                status=["Picking"],
                lookback_hours=48.0,
                outsourced_file="outsourced_products.txt",
                dry_run=False,
            )

            mock_packages = [
                {"orderNumber": "1001", "shipmentPackageId": 5001, "cargoProviderName": "DHL"},
                {"orderNumber": "1002", "shipmentPackageId": 5002, "cargoProviderName": "DHL"},
            ]
            with patch.object(tw.tl, "fetch_packages", return_value=mock_packages):
                attempts = {}
                tw.poll_once(opts, state, attempts, seller, baseline_only=True)

                self.assertIn("5001", state["packages"])
                self.assertEqual(state["packages"]["5001"]["action"], "baseline")
                self.assertIn("5002", state["packages"])
                self.assertEqual(state["packages"]["5002"]["action"], "baseline")


if __name__ == "__main__":
    unittest.main()
