"""Resolve bundled resources, per-user writable application data paths, and backups."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

APP_NAME = "Luma"
DEFAULT_DATA_FILES = ("products.json", "outsourced_products.txt")
MIGRATABLE_DATA_FILES = {
    "products.json": ("products.json", "data/products.json"),
    "outsourced_products.txt": ("outsourced_products.txt", "data/outsourced_products.txt"),
    "unknown_products.json": ("unknown_products.json", "data/unknown_products.json"),
    "printed_packages.json": ("printed_packages.json", "data/printed_packages.json"),
    os.path.join("data", "sellers.json"): (os.path.join("data", "sellers.json"),),
}
MAX_BACKUP_RETENTION = 30


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_project_root() -> Path:
    """Return the source project root or PyInstaller's bundled resource directory."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """Return the writable data root, isolated per Windows user when packaged."""
    if not is_frozen():
        return get_project_root()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not set; cannot determine where to store Luma data.")
    return Path(local_app_data) / APP_NAME


def get_data_path(name: str) -> Path:
    return get_data_dir() / name


def prune_backups(backup_dir: str | Path, prefix: str, keep: int = MAX_BACKUP_RETENTION) -> List[Path]:
    """Prune older backups matching prefix in backup_dir, retaining the most recent `keep` files."""
    backup_path = Path(backup_dir)
    if not backup_path.is_dir():
        return []

    backups = sorted(
        [p for p in backup_path.iterdir() if p.is_file() and p.name.startswith(prefix) and p.suffix == ".json"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    removed = []
    for old_backup in backups[keep:]:
        try:
            old_backup.unlink()
            removed.append(old_backup)
        except OSError:
            pass
    return removed


def find_latest_backup(backup_dir: str | Path, prefix: str) -> Optional[Path]:
    """Find the most recent valid backup file matching prefix."""
    backup_path = Path(backup_dir)
    if not backup_path.is_dir():
        return None

    backups = sorted(
        [p for p in backup_path.iterdir() if p.is_file() and p.name.startswith(prefix) and p.suffix == ".json" and p.stat().st_size > 0],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return backups[0] if backups else None


def initialize_runtime_data() -> None:
    """Create user data directories and install default catalog/rules only once."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    for folder in ("data", "labels_out", "outsourced_labels"):
        (data_dir / folder).mkdir(parents=True, exist_ok=True)

    if is_frozen():
        executable_dir = Path(sys.executable).resolve().parent
        legacy_roots = (executable_dir, executable_dir.parent, Path.cwd())
        for target_name, source_names in MIGRATABLE_DATA_FILES.items():
            target = data_dir / target_name
            if target.exists():
                continue
            for root in dict.fromkeys(legacy_roots):
                if root == data_dir:
                    continue
                source = next(
                    (root / name for name in source_names if (root / name).is_file()),
                    None,
                )
                if source is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    break

    bundle_dir = get_project_root()
    for filename in DEFAULT_DATA_FILES:
        target = data_dir / filename
        bundled_default = bundle_dir / filename
        if not target.exists() and bundled_default.exists():
            shutil.copy2(bundled_default, target)

    unknown_products = data_dir / "unknown_products.json"
    if not unknown_products.exists():
        unknown_products.write_text("{}\n", encoding="utf-8")
