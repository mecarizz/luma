"""Check, verify, and stage Luma updates from public GitHub releases."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Optional, Tuple

import requests

from core.paths import get_data_path

REPOSITORY = "mecarizz/lumapublic"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASE_ASSET = "Luma-windows-x64.zip"
CHECKSUM_ASSET = f"{RELEASE_ASSET}.sha256"
MAX_RELEASE_SIZE = 250 * 1024 * 1024
MAX_EXECUTABLE_SIZE = 150 * 1024 * 1024


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    tag: str
    title: str
    notes: str
    page_url: str
    asset_url: str
    checksum_url: str


def _version_tuple(value: str) -> Tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+(?:\.\d+){1,3})", str(value).strip())
    if not match:
        raise ValueError(f"Unsupported release version tag: {value!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def get_latest_release(current_version: str) -> Optional[UpdateRelease]:
    response = requests.get(
        RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Luma-Updater"},
        timeout=(5, 15),
    )
    if response.status_code == 404:
        raise RuntimeError("No published Luma release was found on GitHub yet.")
    response.raise_for_status()
    release = response.json()

    tag = str(release.get("tag_name") or "")
    version = tag.removeprefix("v")
    if _version_tuple(version) <= _version_tuple(current_version):
        return None

    assets = {
        asset.get("name"): asset.get("browser_download_url")
        for asset in release.get("assets", [])
        if isinstance(asset, dict)
    }
    asset_url = assets.get(RELEASE_ASSET)
    checksum_url = assets.get(CHECKSUM_ASSET)
    if not asset_url or not checksum_url:
        raise RuntimeError(
            f"Release {tag} is missing {RELEASE_ASSET} or its SHA-256 checksum."
        )
    asset_prefix = f"https://github.com/{REPOSITORY}/releases/download/"
    if not asset_url.startswith(asset_prefix) or not checksum_url.startswith(asset_prefix):
        raise RuntimeError("GitHub returned an unexpected release asset URL.")

    return UpdateRelease(
        version=version,
        tag=tag,
        title=str(release.get("name") or f"Luma {tag}"),
        notes=str(release.get("body") or ""),
        page_url=str(release.get("html_url") or ""),
        asset_url=asset_url,
        checksum_url=checksum_url,
    )


def _download(url: str, destination: Path, size_limit: int) -> None:
    response = requests.get(
        url,
        headers={"User-Agent": "Luma-Updater"},
        stream=True,
        timeout=(10, 60),
    )
    response.raise_for_status()
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > size_limit:
        raise RuntimeError("The update download exceeds the permitted size.")

    total = 0
    with destination.open("wb") as target:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > size_limit:
                raise RuntimeError("The update download exceeds the permitted size.")
            target.write(chunk)


def download_update(release: UpdateRelease) -> Path:
    """Download, verify, and safely extract the new executable to user data."""
    updates_dir = get_data_path("updates")
    updates_dir.mkdir(parents=True, exist_ok=True)
    archive_path = updates_dir / RELEASE_ASSET
    checksum_path = updates_dir / CHECKSUM_ASSET
    executable_path = updates_dir / "Luma.new.exe"
    temporary_executable = updates_dir / "Luma.new.exe.tmp"

    try:
        _download(release.checksum_url, checksum_path, 4096)
        checksum_text = checksum_path.read_text(encoding="ascii").strip()
        match = re.fullmatch(r"([0-9a-fA-F]{64})(?:\s+[* ]?.+)?", checksum_text)
        if not match:
            raise RuntimeError("The release SHA-256 checksum file is invalid.")
        expected_hash = match.group(1).lower()

        _download(release.asset_url, archive_path, MAX_RELEASE_SIZE)
        hasher = hashlib.sha256()
        with archive_path.open("rb") as archive_file:
            for chunk in iter(lambda: archive_file.read(1024 * 1024), b""):
                hasher.update(chunk)
        actual_hash = hasher.hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError("The downloaded update failed its SHA-256 checksum.")

        with zipfile.ZipFile(archive_path) as archive:
            matches = [
                item for item in archive.infolist()
                if PurePosixPath(item.filename).name == "Luma.exe"
                and not item.is_dir()
            ]
            if len(matches) != 1 or matches[0].file_size > MAX_EXECUTABLE_SIZE:
                raise RuntimeError("The release archive does not contain one valid Luma.exe.")

            executable = matches[0]
            with archive.open(executable) as source, temporary_executable.open("wb") as target:
                total = 0
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_EXECUTABLE_SIZE:
                        raise RuntimeError("The executable exceeds the permitted size.")
                    target.write(chunk)
        os.replace(temporary_executable, executable_path)
        return executable_path
    except Exception:
        for path in (temporary_executable, executable_path):
            if path.exists():
                path.unlink()
        raise
    finally:
        for path in (archive_path, checksum_path):
            if path.exists():
                path.unlink()


def launch_update(staged_executable: Path) -> None:
    """Launch a small Windows command helper that replaces the app after exit."""
    if not getattr(sys, "frozen", False) or not sys.platform.startswith("win"):
        raise RuntimeError("Installing updates is supported only in the packaged Windows app.")

    current_executable = Path(sys.executable).resolve()
    if not current_executable.is_file() or not staged_executable.is_file():
        raise FileNotFoundError("The current or downloaded Luma executable could not be found.")

    helper_path = Path(tempfile.gettempdir()) / f"luma-update-{os.getpid()}.cmd"
    helper_path.write_text(
        "\r\n".join(
            (
                "@echo off",
                "setlocal DisableDelayedExpansion",
                ":wait_for_luma",
                'tasklist /FI "PID eq %~1" /NH | findstr /C:" %~1 " >nul',
                "if not errorlevel 1 (",
                "  timeout /t 1 /nobreak >nul",
                "  goto wait_for_luma",
                ")",
                'move /Y "%~2" "%~3" >nul',
                "if errorlevel 1 exit /b 1",
                'start "" "%~3"',
                'del "%~f0"',
                "",
            )
        ),
        encoding="ascii",
    )

    command = f'"{helper_path}" "{os.getpid()}" "{staged_executable}" "{current_executable}"'
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["cmd.exe", "/c", command], creationflags=flags, close_fds=True)
