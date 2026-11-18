"""Persistent daily numbering for packages sent to a printer."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Mapping, Optional

from PySide6.QtCore import QLockFile

from core.paths import get_data_path

TR_TZ = timezone(timedelta(hours=3))
RESET_HOUR = 23


def _business_day(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(TR_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=TR_TZ)
    else:
        current = current.astimezone(TR_TZ)
    if current.hour < RESET_HOUR:
        current -= timedelta(days=1)
    return current.date().isoformat()


def reserve_print_numbers(
    packages: Iterable[Mapping[str, object]],
    now: Optional[datetime] = None,
) -> Dict[str, int]:
    package_ids = []
    for package in packages:
        package_id = package.get("shipmentPackageId")
        if package_id is None or not str(package_id).strip():
            raise ValueError("Cannot number a package without a shipment package ID.")
        package_ids.append(str(package_id))
    if not package_ids:
        return {}

    state_path = get_data_path("label_sequence.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(get_data_path("label_sequence.lock")))
    if not lock.tryLock(5000):
        if lock.error() == QLockFile.LockError.LockFailedError:
            raise TimeoutError("Timed out waiting for the label-number counter.")
        raise OSError(f"Could not lock the label-number counter: {lock.error()}")

    try:
        cycle_date = _business_day(now)
        if state_path.exists():
            with state_path.open(encoding="utf-8") as state_file:
                state = json.load(state_file)
            if not isinstance(state, dict):
                raise ValueError(f"Invalid label-number state in {state_path}.")
        else:
            state = {}

        if state.get("cycle_date") != cycle_date:
            state = {
                "cycle_date": cycle_date,
                "next_number": 1,
                "package_numbers": {},
            }

        next_number = state.get("next_number")
        package_numbers = state.get("package_numbers")
        if (
            not isinstance(next_number, int)
            or isinstance(next_number, bool)
            or next_number < 1
            or not isinstance(package_numbers, dict)
        ):
            raise ValueError(f"Invalid label-number state in {state_path}.")

        reserved = {}
        for package_id in package_ids:
            number = package_numbers.get(package_id)
            if number is None:
                number = next_number
                next_number += 1
                package_numbers[package_id] = number
            if not isinstance(number, int) or isinstance(number, bool) or number < 1:
                raise ValueError(f"Invalid label number for package {package_id}.")
            reserved[package_id] = number
        state["next_number"] = next_number

        temporary_path = state_path.with_suffix(state_path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as state_file:
            json.dump(state, state_file, ensure_ascii=False, indent=1)
            state_file.flush()
            os.fsync(state_file.fileno())
        os.replace(temporary_path, state_path)
        return reserved
    finally:
        lock.unlock()
