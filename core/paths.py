"""Resolve bundled resources and per-user writable application data paths."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Luma"
DEFAULT_DATA_FILES = ("products.json", "outsourced_products.txt")
MIGRATABLE_DATA_FILES = {
    "products.json": ("products.json", "data/products.json"),
    "outsourced_products.txt": ("outsourced_products.txt", "data/outsourced_products.txt"),
    "unknown_products.json": ("unknown_products.json", "data/unknown_products.json"),
    "printed_packages.json": ("printed_packages.json", "data/printed_packages.json"),
    os.path.join("data", "sellers.json"): (os.path.join("data", "sellers.json"),),
}


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
