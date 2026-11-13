"""Unit tests for centralized configuration and hardware defaults."""
import os
import unittest
from core.config import (
    DEFAULT_LABEL_SIZE,
    DEFAULT_LABEL_SHIFT_Y_MM,
    DEFAULT_PRINTER_NAME,
    DEFAULT_SUMATRA_PATH,
    AppConfig,
    SellerConfig,
    get_config,
    load_sellers_from_env,
    mask_secret,
    parse_label_size,
)


class TestConfig(unittest.TestCase):
    def test_hardware_defaults(self):
        """Verify label layout defaults and use of the client system printer."""
        self.assertEqual(DEFAULT_LABEL_SIZE, "100x100")
        self.assertEqual(DEFAULT_LABEL_SHIFT_Y_MM, 29.0)
        self.assertEqual(DEFAULT_PRINTER_NAME, "")
        self.assertIn("SumatraPDF.exe", DEFAULT_SUMATRA_PATH)

    def test_parse_label_size(self):
        self.assertEqual(parse_label_size("100x100"), (100.0, 100.0))
        self.assertEqual(parse_label_size(" 100X150 "), (100.0, 150.0))

        with self.assertRaises(ValueError):
            parse_label_size("invalid")

        with self.assertRaises(ValueError):
            parse_label_size("-100x100")

    def test_mask_secret(self):
        self.assertEqual(mask_secret(""), "(none)")
        self.assertEqual(mask_secret("123"), "***")
        masked = mask_secret("my_secret_key_12345")
        self.assertTrue(masked.startswith("my_"))
        self.assertTrue(masked.endswith("345 (len 19)"))
        self.assertNotIn("secret_key", masked)

    def test_seller_loading_numbered(self):
        old_env = os.environ.copy()
        try:
            os.environ["TRENDYOL_SELLER_ID_1"] = "674974"
            os.environ["TRENDYOL_API_KEY_1"] = "key1"
            os.environ["TRENDYOL_API_SECRET_1"] = "secret1"
            os.environ["TRENDYOL_SELLER_NAME_1"] = "Loria"

            os.environ["TRENDYOL_SELLER_ID_2"] = "1234567"
            os.environ["TRENDYOL_API_KEY_2"] = "key2"
            os.environ["TRENDYOL_API_SECRET_2"] = "secret2"
            os.environ["TRENDYOL_SELLER_NAME_2"] = "Ayla Home"

            for i in range(3, 21):
                os.environ.pop(f"TRENDYOL_SELLER_ID_{i}", None)
            os.environ.pop("TRENDYOL_SELLER_ID", None)

            sellers = load_sellers_from_env()
            self.assertEqual(len(sellers), 2)
            self.assertEqual(sellers[0].id, "674974")
            self.assertEqual(sellers[0].name, "Loria")
            self.assertEqual(sellers[1].id, "1234567")
            self.assertEqual(sellers[1].name, "Ayla Home")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_duplicate_seller_id_rejected(self):
        old_env = os.environ.copy()
        try:
            os.environ["TRENDYOL_SELLER_ID_1"] = "674974"
            os.environ["TRENDYOL_API_KEY_1"] = "k1"
            os.environ["TRENDYOL_API_SECRET_1"] = "s1"
            os.environ["TRENDYOL_SELLER_ID_2"] = "674974"  # Duplicate
            os.environ["TRENDYOL_API_KEY_2"] = "k2"
            os.environ["TRENDYOL_API_SECRET_2"] = "s2"

            with self.assertRaises(ValueError):
                load_sellers_from_env()
        finally:
            os.environ.clear()
            os.environ.update(old_env)


if __name__ == "__main__":
    unittest.main()
