"""Unit tests for the OutsourcedClassifier engine."""
import os
import shutil
import tempfile
import unittest
from core.classifier import OutsourcedClassifier


class TestClassifier(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_duplicate_and_redundant_rules_detection(self):
        rule_file = os.path.join(self.test_dir, "outsourced.txt")
        content = (
            "# Outsourced items\n"
            "LHLP*      # Wildcard for all Loria\n"
            "LHLPK      # Redundant! Covered by LHLP*\n"
            "AYKK45     # Ayla kirlent\n"
            "aykk45     # Exact duplicate!\n"
        )
        with open(rule_file, "w", encoding="utf-8") as f:
            f.write(content)

        classifier = OutsourcedClassifier(rule_file)
        report = classifier.load(force=True)

        self.assertIn("AYKK45", report.duplicates)
        self.assertTrue(any(red[0] == "LHLPK" and red[1] == "LHLP*" for red in report.redundant_rules))
        # Unique valid rules preserved (duplicate excluded, redundant noted in report)
        self.assertEqual(len(classifier.patterns), 3)
        self.assertIn("LHLP*", classifier.patterns)
        self.assertIn("LHLPK", classifier.patterns)
        self.assertIn("AYKK45", classifier.patterns)

    def test_line_by_line_routing_attribution(self):
        rule_file = os.path.join(self.test_dir, "outsourced.txt")
        with open(rule_file, "w", encoding="utf-8") as f:
            f.write("AYKK45*\n")

        classifier = OutsourcedClassifier(rule_file)
        pkg = {
            "orderNumber": "99001",
            "lines": [
                {"barcode": "LHLPK", "productName": "Loria Nevresim", "quantity": 1},
                {"barcode": "AYKK45", "productName": "Ayla Kırlent", "quantity": 2},
            ]
        }
        res = classifier.route_package(pkg, mixed_mode="both")
        self.assertEqual(res.kind, "mixed")
        self.assertTrue(res.do_print)
        self.assertTrue(res.do_save)
        self.assertEqual(len(res.matched_lines), 1)
        self.assertEqual(res.matched_lines[0]["barcode"], "AYKK45")
        self.assertEqual(len(res.unmatched_lines), 1)
        self.assertEqual(res.unmatched_lines[0]["barcode"], "LHLPK")
        self.assertIn("AYKK45*", res.matched_rules)


if __name__ == "__main__":
    unittest.main()
