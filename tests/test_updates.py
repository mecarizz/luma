import base64
import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from core import updates


class TestUpdates(unittest.TestCase):
    def test_updates_target_the_published_repository(self):
        self.assertEqual(updates.REPOSITORY, "mecarizz/luma")
        self.assertEqual(
            updates.RELEASE_API,
            "https://api.github.com/repos/mecarizz/luma/releases/latest",
        )

    def test_version_comparison(self):
        self.assertEqual(updates._version_tuple("v1.2.3"), (1, 2, 3))
        with self.assertRaises(ValueError):
            updates._version_tuple("latest")

    def test_update_importance_defaults_to_normal_and_parses_levels(self):
        self.assertEqual(updates._update_importance("Bug fixes and improvements."), 1)
        self.assertEqual(
            updates._update_importance("Release summary\nLuma-Update-Level: 2"),
            2,
        )
        self.assertEqual(updates._update_importance("Luma-Update-Level: 3"), 3)

    def test_update_importance_rejects_invalid_level(self):
        for notes in ("Luma-Update-Level: 0", "Luma-Update-Level: 4", "Luma-Update-Level: urgent"):
            with self.subTest(notes=notes):
                with self.assertRaisesRegex(ValueError, "must be 1, 2, or 3"):
                    updates._update_importance(notes)

    def test_latest_release_requires_archive_and_checksum(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "tag_name": "v1.1.0",
            "name": "Luma 1.1.0",
            "body": "Release notes\nLuma-Update-Level: 2",
            "assets": [
                {
                    "name": updates.RELEASE_ASSET,
                    "browser_download_url": "https://github.com/mecarizz/luma/releases/download/v1.1.0/Luma-windows-x64.zip",
                },
                {
                    "name": updates.CHECKSUM_ASSET,
                    "browser_download_url": "https://github.com/mecarizz/luma/releases/download/v1.1.0/Luma-windows-x64.zip.sha256",
                },
            ],
        }
        with patch.object(updates.requests, "get", return_value=response):
            release = updates.get_latest_release("1.0.0")
        self.assertEqual(release.version, "1.1.0")
        self.assertEqual(release.importance_level, 2)
        self.assertEqual(release.notes, "Release notes")

    def test_current_version_returns_no_update(self):
        response = Mock(status_code=200)
        response.json.return_value = {"tag_name": "v1.0.0", "assets": []}
        with patch.object(updates.requests, "get", return_value=response):
            self.assertIsNone(updates.get_latest_release("1.0.0"))

    def test_update_download_checks_checksum_and_extracts_only_executable(self):
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("Luma.exe", b"test executable")
            archive.writestr("../../unexpected.txt", b"ignored")
        payload = archive_bytes.getvalue()
        checksum = f"{hashlib.sha256(payload).hexdigest()}  {updates.RELEASE_ASSET}\n"

        checksum_response = Mock(headers={})
        checksum_response.iter_content.return_value = [checksum.encode("ascii")]
        checksum_response.raise_for_status.return_value = None
        archive_response = Mock(headers={"Content-Length": str(len(payload))})
        archive_response.iter_content.return_value = [payload]
        archive_response.raise_for_status.return_value = None
        release = updates.UpdateRelease(
            version="1.1.0",
            tag="v1.1.0",
            title="Luma 1.1.0",
            notes="",
            page_url="",
            asset_url="https://github.com/mecarizz/luma/releases/download/v1.1.0/Luma-windows-x64.zip",
            checksum_url="https://github.com/mecarizz/luma/releases/download/v1.1.0/Luma-windows-x64.zip.sha256",
        )

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(updates, "get_data_path", return_value=Path(directory)):
                with patch.object(updates.requests, "get", side_effect=[checksum_response, archive_response]):
                    staged = updates.download_update(release)
            self.assertEqual(staged.read_bytes(), b"test executable")
            self.assertFalse((Path(directory) / updates.RELEASE_ASSET).exists())
            self.assertFalse((Path(directory) / updates.CHECKSUM_ASSET).exists())

    def test_update_download_rejects_bad_checksum(self):
        checksum_response = Mock(headers={})
        checksum_response.iter_content.return_value = [b"0" * 64]
        checksum_response.raise_for_status.return_value = None
        archive_response = Mock(headers={})
        archive_response.iter_content.return_value = [b"not a zip"]
        archive_response.raise_for_status.return_value = None
        release = updates.UpdateRelease(
            version="1.1.0",
            tag="v1.1.0",
            title="Luma 1.1.0",
            notes="",
            page_url="",
            asset_url="https://github.com/mecarizz/luma/releases/download/v1.1.0/Luma-windows-x64.zip",
            checksum_url="https://github.com/mecarizz/luma/releases/download/v1.1.0/Luma-windows-x64.zip.sha256",
        )

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(updates, "get_data_path", return_value=Path(directory)):
                with patch.object(updates.requests, "get", side_effect=[checksum_response, archive_response]):
                    with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                        updates.download_update(release)
            self.assertFalse((Path(directory) / "Luma.new.exe").exists())

    def test_install_update_uses_versioned_per_user_path_and_creates_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            staged = data_dir / "updates" / "Luma.new.exe"
            staged.parent.mkdir()
            staged.write_bytes(b"new executable")
            old_executable = data_dir / "Program Files" / "Luma.exe"
            old_executable.parent.mkdir()
            old_executable.write_bytes(b"old executable")

            with patch.object(
                updates,
                "get_data_path",
                side_effect=lambda name: data_dir / name,
            ), \
                    patch.object(updates.sys, "frozen", True, create=True), \
                    patch.object(updates.sys, "platform", "win32"), \
                    patch.object(updates, "_create_desktop_shortcut") as create_shortcut:
                installed = updates.install_update(staged, "1.0.4")

            self.assertEqual(installed, data_dir / "app" / "v1.0.4" / "Luma.exe")
            self.assertEqual(installed.read_bytes(), b"new executable")
            self.assertEqual(old_executable.read_bytes(), b"old executable")
            self.assertFalse(staged.exists())
            create_shortcut.assert_called_once_with(installed, "1.0.4")

    def test_install_update_rejects_invalid_version_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            staged = data_dir / "Luma.new.exe"
            staged.write_bytes(b"new executable")

            with patch.object(
                updates,
                "get_data_path",
                side_effect=lambda name: data_dir / name,
            ), \
                    patch.object(updates.sys, "frozen", True, create=True), \
                    patch.object(updates.sys, "platform", "win32"):
                with self.assertRaisesRegex(ValueError, "Unsupported release version"):
                    updates.install_update(staged, "../outside")

            self.assertFalse((data_dir / "app").exists())

    def test_desktop_shortcut_uses_escaped_encoded_powershell(self):
        result = Mock(returncode=0, stdout="", stderr="")
        executable = Path("C:/Users/O'Brien/AppData/Local/Luma/app/v1.0.4/Luma.exe")

        with patch.object(updates.subprocess, "run", return_value=result) as run:
            updates._create_desktop_shortcut(executable, "1.0.4")

        command = run.call_args.args[0]
        script = base64.b64decode(command[-1]).decode("utf-16le")
        self.assertIn("O''Brien", script)
        self.assertIn("Luma v1.0.4.lnk", script)
        self.assertIn("SpecialFolders('Desktop')", script)
        self.assertNotIn("runas", command)

    def test_launch_update_starts_installed_executable_without_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Luma.exe"
            executable.write_bytes(b"new executable")

            with patch.object(updates.sys, "frozen", True, create=True), \
                    patch.object(updates.sys, "platform", "win32"), \
                    patch.object(updates.subprocess, "Popen") as popen:
                updates.launch_update(executable)

            args, kwargs = popen.call_args
            self.assertEqual(args[0], [str(executable)])
            self.assertEqual(kwargs["cwd"], str(executable.parent))
            self.assertTrue(kwargs["close_fds"])


if __name__ == "__main__":
    unittest.main()
