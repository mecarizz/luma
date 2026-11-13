import unittest

from core.i18n import SUPPORTED_LANGUAGES, tr


class TestTranslations(unittest.TestCase):
    def test_supported_languages_are_english_and_turkish(self):
        self.assertEqual(SUPPORTED_LANGUAGES, ("en", "tr"))

    def test_turkish_translation_and_formatting(self):
        message = tr("Printed {count} label(s).", "tr").format(count=3)
        self.assertEqual(message, "3 etiket yazdırıldı.")

    def test_product_catalog_translations_and_formatting(self):
        self.assertEqual(tr("Add Product", "tr"), "Ürün Ekle")
        self.assertEqual(tr("Barcode", "tr"), "Barkod")
        summary = tr("{visible} products shown · {total} total", "tr").format(
            visible=2,
            total=5,
        )
        self.assertEqual(summary, "2 ürün gösteriliyor · toplam 5")

    def test_unknown_text_falls_back_to_english(self):
        self.assertEqual(tr("A new technical message", "tr"), "A new technical message")

    def test_english_translation_is_unchanged(self):
        self.assertEqual(tr("Orders & Labels", "en"), "Orders & Labels")


if __name__ == "__main__":
    unittest.main()
