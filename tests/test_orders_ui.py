import unittest
from unittest.mock import patch

from core.security import encrypt_secret
from core.seller_models import SellerProfile
from ui_orders import _FetchOrdersWorker


class TestFetchOrdersWorker(unittest.TestCase):
    def setUp(self):
        self.profile = SellerProfile(
            seller_id="123456",
            name="Test Seller",
            api_key=encrypt_secret("test-key"),
            api_secret=encrypt_secret("test-secret"),
            statuses=["Created", "Picking"],
            lookback_hours=48,
        )

    def test_fetch_uses_saved_profile_credentials_statuses_and_lookback(self):
        package = {"shipmentPackageId": 10}
        results = []
        logs = []
        worker = _FetchOrdersWorker([self.profile])
        worker.completed.connect(results.append)
        worker.log_emitted.connect(logs.append)

        with patch("trendyol_labels.fetch_packages", return_value=[package]) as fetch:
            worker.run()

        fetch.assert_called_once_with(
            ["Created", "Picking"],
            2,
            seller={
                "id": "123456",
                "key": "test-key",
                "secret": "test-secret",
                "name": "Test Seller",
                "cargo": "DHLECOMMP",
            },
        )
        self.assertEqual(results, [([package], [])])
        self.assertTrue(any("Manual order fetch started" in line for line in logs))
        self.assertTrue(any("Manual order fetch completed" in line for line in logs))

    def test_fetch_reports_trendyol_errors_to_the_ui(self):
        results = []
        worker = _FetchOrdersWorker([self.profile])
        worker.completed.connect(results.append)

        with patch("trendyol_labels.fetch_packages", side_effect=SystemExit("403: invalid API access")):
            worker.run()

        self.assertEqual(results[0][0], [])
        self.assertIn("403: invalid API access", results[0][1][0])

    def test_fetch_does_not_send_dpapi_ciphertext_as_api_credentials(self):
        self.profile.api_key = "dpapi:encrypted-key"
        self.profile.api_secret = "dpapi:encrypted-secret"
        results = []
        worker = _FetchOrdersWorker([self.profile])
        worker.completed.connect(results.append)

        with patch("core.seller_models.decrypt_secret", side_effect=lambda value: value):
            with patch("trendyol_labels.fetch_packages") as fetch:
                worker.run()

        fetch.assert_not_called()
        self.assertIn("could not be decrypted", results[0][1][0])


if __name__ == "__main__":
    unittest.main()
