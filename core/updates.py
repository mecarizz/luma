"""Check, verify, and stage Luma updates from public GitHub releases."""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from typing import Optional, Tuple

import requests

from core.paths import get_data_path

REPOSITORY = "mecarizz/luma"
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
    importance_level: int = 1


def _version_tuple(value: str) -> Tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+(?:\.\d+){1,3})", str(value).strip())
    if not match:
        raise ValueError(f"Unsupported release version tag: {value!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def _update_importance(notes: str) -> int:
    match = re.search(
        r"(?im)^\s*Luma-Update-Level:\s*(\S+)\s*$",
        notes,
    )
    if match is None:
        return 1
    try:
        level = int(match.group(1))
    except ValueError as exc:
        raise ValueError("Luma-Update-Level must be 1, 2, or 3.") from exc
    if level not in (1, 2, 3):
        raise ValueError("Luma-Update-Level must be 1, 2, or 3.")
    return level


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

    notes = str(release.get("body") or "")
    importance_level = _update_importance(notes)
    display_notes = re.sub(
        r"(?im)^\s*Luma-Update-Level:\s*\S+\s*$",
        "",
        notes,
    ).strip()
    return UpdateRelease(
        version=version,
        tag=tag,
        title=str(release.get("name") or f"Luma {tag}"),
        notes=display_notes,
        page_url=str(release.get("html_url") or ""),
        asset_url=asset_url,
        checksum_url=checksum_url,
        importance_level=importance_level,
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


def _powershell_literal(value: str) -> str:
    """Return a single-quoted PowerShell string literal."""
    return "'" + value.replace("'", "''") + "'"


def _create_desktop_shortcut(executable: Path, version: str) -> None:
    shortcut_name = f"Luma v{version}.lnk"
    script = "\n".join(
        (
            "$ErrorActionPreference = 'Stop'",
            "$shell = New-Object -ComObject WScript.Shell",
            "$desktop = $shell.SpecialFolders('Desktop')",
            f"$target = {_powershell_literal(str(executable))}",
            f"$name = {_powershell_literal(shortcut_name)}",
            "$shortcutPath = Join-Path $desktop $name",
            "$shortcut = $shell.CreateShortcut($shortcutPath)",
            "$shortcut.TargetPath = $target",
            "$shortcut.WorkingDirectory = Split-Path -Parent $target",
            "$shortcut.Description = 'Luma Trendyol Manager'",
            "$shortcut.IconLocation = $target + ',0'",
            "$shortcut.Save()",
            "if (-not (Test-Path -LiteralPath $shortcutPath)) { throw 'Shortcut was not created.' }",
        )
    )
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded_script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            "Could not create the Luma desktop shortcut"
            + (f": {details}" if details else ".")
        )


def install_update(staged_executable: Path, version: str) -> Path:
    """Install a verified release into the current user's writable app-data folder."""
    if not getattr(sys, "frozen", False) or not sys.platform.startswith("win"):
        raise RuntimeError("Installing updates is supported only in the packaged Windows app.")

    if not staged_executable.is_file():
        raise FileNotFoundError("The downloaded Luma executable could not be found.")

    normalized_version = ".".join(str(part) for part in _version_tuple(version))
    install_dir = get_data_path("app") / f"v{normalized_version}"
    install_dir.mkdir(parents=True, exist_ok=True)
    installed_executable = install_dir / "Luma.exe"
    temporary_executable = install_dir / "Luma.exe.tmp"

    try:
        shutil.copy2(staged_executable, temporary_executable)
        os.replace(temporary_executable, installed_executable)
        _create_desktop_shortcut(installed_executable, normalized_version)
    except Exception:
        if temporary_executable.exists():
            temporary_executable.unlink()
        raise

    staged_executable.unlink()
    return installed_executable


def launch_update(installed_executable: Path) -> None:
    """Launch the installed per-user update without elevation."""
    if not getattr(sys, "frozen", False) or not sys.platform.startswith("win"):
        raise RuntimeError("Installing updates is supported only in the packaged Windows app.")
    if not installed_executable.is_file():
        raise FileNotFoundError("The installed Luma executable could not be found.")

    flags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
    )
    subprocess.Popen(
        [str(installed_executable)],
        cwd=str(installed_executable.parent),
        creationflags=flags,
        close_fds=True,
    )
