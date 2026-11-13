import os
import tempfile
import unittest
from unittest.mock import patch

from core.seller_manager import SellerManager
from core.seller_models import SellerProfile


class TestSellerManager(unittest.TestCase):
    def test_empty_manager_does_not_create_fake_sellers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "sellers.json")
            with patch.dict(os.environ, {}, clear=True):
                manager = SellerManager(path)

            self.assertEqual(manager.list_all(), [])
            self.assertFalse(os.path.exists(path))

    def test_seller_id_and_credentials_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "sellers.json")
            with patch.dict(os.environ, {}, clear=True):
                manager = SellerManager(path)
                profile = SellerProfile(
                    seller_id=" 123456 ",
                    name="Test Shop",
                    api_key="test-api-key",
                    api_secret="test-api-secret",
                )
                self.assertEqual(manager.save_profile(profile), [])

                loaded = SellerManager(path).get("123456")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.name, "Test Shop")
            self.assertEqual(loaded.raw_api_key, "test-api-key")
            self.assertEqual(loaded.raw_api_secret, "test-api-secret")

    def test_missing_seller_id_and_credentials_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                manager = SellerManager(os.path.join(directory, "sellers.json"))

            errors = manager.save_profile(SellerProfile(seller_id=""))
            self.assertIn("Seller ID is required.", errors)
            self.assertIn("Trendyol API Key is required.", errors)
            self.assertIn("Trendyol API Secret is required.", errors)

    def test_failed_dpapi_decryption_is_reported_as_unavailable_credentials(self):
        profile = SellerProfile(
            seller_id="123456",
            api_key="dpapi:encrypted-key",
            api_secret="dpapi:encrypted-secret",
        )

        with patch("core.seller_models.decrypt_secret", side_effect=lambda value: value):
            self.assertIn("could not be decrypted", profile.credential_error)


if __name__ == "__main__":
    unittest.main()
