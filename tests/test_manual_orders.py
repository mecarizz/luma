import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.manual_orders import prepare_package_for_cargo


class TestManualOrders(unittest.TestCase):
    def test_package_already_using_requested_carrier_is_not_switched(self):
        package = {"shipmentPackageId": 123, "cargoProviderCode": "TEX"}
        seller = {"id": "456", "key": "key", "secret": "secret", "cargo": "DHLECOMMP"}

        with patch("trendyol_watcher.switch_to_cargo") as switch:
            result = prepare_package_for_cargo(package, seller, SimpleNamespace(), "TEX")

        self.assertIs(result, package)
        switch.assert_not_called()

    def test_switched_package_returns_refreshed_tracking_data(self):
        package = {
            "shipmentPackageId": 123,
            "orderNumber": "order-1",
            "cargoProviderCode": "TEX",
        }
        refreshed = {
            "shipmentPackageId": 123,
            "orderNumber": "order-1",
            "cargoProviderCode": "DHLECOMMP",
            "cargoTrackingNumber": "DHL-tracking",
        }
        seller = {"id": "456", "key": "key", "secret": "secret", "cargo": "TEX"}
        options = SimpleNamespace(status=["Picking"])

        with patch("trendyol_watcher.switch_to_cargo", return_value=(True, "ok")) as switch:
            with patch("trendyol_watcher.refetch_as_cargo", return_value=refreshed) as refetch:
                result = prepare_package_for_cargo(package, seller, options, "DHLECOMMP")

        self.assertEqual(result["cargoTrackingNumber"], "DHL-tracking")
        switch.assert_called_once_with("123", {**seller, "cargo": "DHLECOMMP"}, "DHLECOMMP")
        refetch.assert_called_once_with(
            package,
            options,
            seller={**seller, "cargo": "DHLECOMMP"},
        )

    def test_switch_failure_is_reported_without_refetching(self):
        package = {"shipmentPackageId": 123, "cargoProviderCode": "TEX"}
        seller = {"id": "456", "key": "key", "secret": "secret"}

        with patch("trendyol_watcher.switch_to_cargo", return_value=(False, "HTTP 400")):
            with patch("trendyol_watcher.refetch_as_cargo") as refetch:
                with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
                    prepare_package_for_cargo(package, seller, SimpleNamespace(), "DHLECOMMP")
        refetch.assert_not_called()

    def test_missing_refreshed_package_is_reported(self):
        package = {"shipmentPackageId": 123, "cargoProviderCode": "TEX"}
        seller = {"id": "456", "key": "key", "secret": "secret"}

        with patch("trendyol_watcher.switch_to_cargo", return_value=(True, "ok")):
            with patch("trendyol_watcher.refetch_as_cargo", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "updated DHLECOMMP tracking barcode"):
                    prepare_package_for_cargo(package, seller, SimpleNamespace(), "DHLECOMMP")


if __name__ == "__main__":
    unittest.main()
