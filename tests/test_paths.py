import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.paths import APP_NAME, get_data_dir, initialize_runtime_data


class TestRuntimePaths(unittest.TestCase):
    def test_frozen_data_dir_is_per_user_local_app_data(self):
        with patch("core.paths.is_frozen", return_value=True):
            with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\worker\AppData\Local"}):
                self.assertEqual(
                    get_data_dir(),
                    Path(r"C:\Users\worker\AppData\Local") / APP_NAME,
                )

    def test_frozen_runtime_copies_defaults_once_and_keeps_user_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            data = root / "user-data"
            bundle.mkdir()
            data.mkdir()
            (bundle / "products.json").write_text('{"bundle": {}}', encoding="utf-8")
            (bundle / "outsourced_products.txt").write_text("RULE*\n", encoding="utf-8")
            (data / "products.json").write_text('{"local": {}}', encoding="utf-8")
            executable_dir = root / "install"
            executable_dir.mkdir()

            with patch("core.paths.is_frozen", return_value=True):
                with patch("core.paths.sys.executable", str(executable_dir / "Luma.exe")):
                    with patch("core.paths.Path.cwd", return_value=root):
                        with patch("core.paths.get_project_root", return_value=bundle):
                            with patch("core.paths.get_data_dir", return_value=data):
                                initialize_runtime_data()

            self.assertEqual((data / "products.json").read_text(encoding="utf-8"), '{"local": {}}')
            self.assertEqual((data / "outsourced_products.txt").read_text(encoding="utf-8"), "RULE*\n")
            self.assertEqual((data / "unknown_products.json").read_text(encoding="utf-8"), "{}\n")
            self.assertTrue((data / "data").is_dir())
            self.assertTrue((data / "labels_out").is_dir())
            self.assertTrue((data / "outsourced_labels").is_dir())

    def test_frozen_runtime_migrates_existing_local_state_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            executable_dir = project / "dist"
            executable_dir.mkdir(parents=True)
            (project / "data").mkdir()
            (project / "data" / "sellers.json").write_text('{"sellers": []}', encoding="utf-8")
            (project / "printed_packages.json").write_text('{"packages": {"1": {}}}', encoding="utf-8")
            (project / "products.json").write_text('{"custom": {}}', encoding="utf-8")
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "products.json").write_text('{"default": {}}', encoding="utf-8")
            (bundle / "outsourced_products.txt").write_text("RULE*\n", encoding="utf-8")
            data = root / "user-data"
            data.mkdir()

            with patch("core.paths.is_frozen", return_value=True):
                with patch("core.paths.sys.executable", str(executable_dir / "Luma.exe")):
                    with patch("core.paths.Path.cwd", return_value=root):
                        with patch("core.paths.get_project_root", return_value=bundle):
                            with patch("core.paths.get_data_dir", return_value=data):
                                initialize_runtime_data()

            self.assertEqual(
                (data / "data" / "sellers.json").read_text(encoding="utf-8"),
                '{"sellers": []}',
            )
            self.assertEqual(
                (data / "printed_packages.json").read_text(encoding="utf-8"),
                '{"packages": {"1": {}}}',
            )
            self.assertEqual(
                (data / "products.json").read_text(encoding="utf-8"),
                '{"custom": {}}',
            )


if __name__ == "__main__":
    unittest.main()
