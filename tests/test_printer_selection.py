import unittest
from types import SimpleNamespace
from unittest.mock import patch

import trendyol_labels


class TestPrinterSelection(unittest.TestCase):
    def test_empty_printer_selection_uses_system_default(self):
        def get_env(name, default=None):
            return {
                "SUMATRA_PATH": "SumatraPDF.exe",
                "PRINTER_NAME": "Legacy printer",
            }.get(name, default)

        with patch.object(trendyol_labels.sys, "platform", "win32"), \
                patch.object(trendyol_labels.os.path, "exists", return_value=True), \
                patch.object(trendyol_labels.os, "getenv", side_effect=get_env), \
                patch("subprocess.run", return_value=SimpleNamespace(returncode=0)) as run:
            result = trendyol_labels.send_to_printer("label.pdf", "")

        self.assertTrue(result)
        command = run.call_args.args[0]
        self.assertEqual(command[1:3], ["-print-to-default", "-print-settings"])

    def test_explicit_printer_is_passed_to_sumatra(self):
        def get_env(name, default=None):
            return {"SUMATRA_PATH": "SumatraPDF.exe"}.get(name, default)

        with patch.object(trendyol_labels.sys, "platform", "win32"), \
                patch.object(trendyol_labels.os.path, "exists", return_value=True), \
                patch.object(trendyol_labels.os, "getenv", side_effect=get_env), \
                patch("subprocess.run", return_value=SimpleNamespace(returncode=0)) as run:
            result = trendyol_labels.send_to_printer("label.pdf", "Client printer")

        self.assertTrue(result)
        command = run.call_args.args[0]
        self.assertEqual(command[1:3], ["-print-to", "Client printer"])


if __name__ == "__main__":
    unittest.main()
