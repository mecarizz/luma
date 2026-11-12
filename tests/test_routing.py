"""Unit tests for product routing and outsourced order classification."""
import unittest
import trendyol_labels as tl


class TestRouting(unittest.TestCase):
    def test_classify_normal_order(self):
        pkg = {
            "lines": [
                {"barcode": "LHLPK", "quantity": 1},
                {"barcode": "NRYK5070", "quantity": 2},
            ]
        }
        patterns = ["aykk*"]
        self.assertEqual(tl.classify(pkg, patterns), "normal")
        kind, do_print, do_save = tl.route(pkg, patterns)
        self.assertEqual(kind, "normal")
        self.assertTrue(do_print)
        self.assertFalse(do_save)

    def test_classify_fully_outsourced_order(self):
        pkg = {
            "lines": [
                {"barcode": "AYKK45", "quantity": 1},
                {"barcode": "AYKK45H", "quantity": 2},
            ]
        }
        patterns = ["aykk*"]
        self.assertEqual(tl.classify(pkg, patterns), "outsourced")
        kind, do_print, do_save = tl.route(pkg, patterns)
        self.assertEqual(kind, "outsourced")
        self.assertFalse(do_print)
        self.assertTrue(do_save)

    def test_classify_mixed_order(self):
        pkg = {
            "lines": [
                {"barcode": "LHLPK", "quantity": 1},   # In-stock
                {"barcode": "AYKK45", "quantity": 2},  # Outsourced
            ]
        }
        patterns = ["aykk*"]
        self.assertEqual(tl.classify(pkg, patterns), "mixed")

        # Default mixed='both'
        kind, do_print, do_save = tl.route(pkg, patterns, mixed="both")
        self.assertEqual(kind, "mixed")
        self.assertTrue(do_print)
        self.assertTrue(do_save)

        # mixed='print'
        _, do_print, do_save = tl.route(pkg, patterns, mixed="print")
        self.assertTrue(do_print)
        self.assertFalse(do_save)

        # mixed='save'
        _, do_print, do_save = tl.route(pkg, patterns, mixed="save")
        self.assertFalse(do_print)
        self.assertTrue(do_save)

    def test_case_insensitive_matching(self):
        pkg = {"lines": [{"barcode": "lhlpg", "quantity": 1}]}
        patterns = ["lhlpg"]
        self.assertEqual(tl.classify(pkg, patterns), "outsourced")

        pkg_upper = {"lines": [{"barcode": "LHLPG", "quantity": 1}]}
        self.assertEqual(tl.classify(pkg_upper, patterns), "outsourced")


if __name__ == "__main__":
    unittest.main()
