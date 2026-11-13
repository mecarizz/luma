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

    def test_latest_release_requires_archive_and_checksum(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "tag_name": "v1.1.0",
            "name": "Luma 1.1.0",
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


if __name__ == "__main__":
    unittest.main()
