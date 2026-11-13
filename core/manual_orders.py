"""Helpers for preparing manually selected Trendyol packages for label printing."""
from __future__ import annotations

from typing import Any, Dict


def prepare_package_for_cargo(
    package: Dict[str, Any],
    seller: Dict[str, str],
    options: Any,
    target_cargo: str,
) -> Dict[str, Any]:
    """Switch one package if needed and return its refreshed carrier barcode data."""
    import trendyol_watcher as watcher

    seller_for_target = {**seller, "cargo": target_cargo}
    if watcher.is_target_cargo(package, target_cargo):
        return package

    package_id = watcher.pid_of(package)
    if package_id in ("", "None"):
        raise ValueError("The selected order has no shipment package ID.")

    switched, message = watcher.switch_to_cargo(package_id, seller_for_target, target_cargo)
    if not switched:
        raise RuntimeError(f"Could not switch package {package_id} to {target_cargo}: {message}")

    refreshed = watcher.refetch_as_cargo(
        package,
        options,
        seller=seller_for_target,
    )
    if refreshed is None:
        raise RuntimeError(
            f"Package {package_id} was switched, but Trendyol did not return its "
            f"updated {target_cargo} tracking barcode."
        )
    return refreshed
