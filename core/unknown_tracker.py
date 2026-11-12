"""Unknown product tracking and discovery registry.

Safely captures unrecognized barcodes from orders, logs metadata, counts occurrences,
and stores entries in unknown_products.json for easy catalog promotion.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.catalog import normalize_identifier


@dataclass
class UnknownProductEntry:
    barcode: str
    stock_code: Optional[str] = None
    trendyol_name: Optional[str] = None
    seller_id: Optional[str] = None
    seller_name: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    occurrence_count: int = 1
    sample_order_number: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UnknownProductEntry:
        return cls(
            barcode=normalize_identifier(data.get("barcode")),
            stock_code=data.get("stock_code") or data.get("stockCode"),
            trendyol_name=data.get("trendyol_name") or data.get("productName"),
            seller_id=data.get("seller_id"),
            seller_name=data.get("seller_name"),
            first_seen=data.get("first_seen"),
            last_seen=data.get("last_seen"),
            occurrence_count=int(data.get("occurrence_count", 1)),
            sample_order_number=data.get("sample_order_number") or data.get("orderNumber"),
        )


class UnknownProductTracker:
    """Manages recording and persistence of unknown barcodes encountered during processing."""

    def __init__(self, file_path: str = "unknown_products.json"):
        self.file_path = file_path
        self._entries: Dict[str, UnknownProductEntry] = {}
        self._last_mtime: float = -1.0
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.file_path) or os.path.getsize(self.file_path) == 0:
            self._entries = {}
            self._last_mtime = -1.0
            return

        try:
            mtime = os.path.getmtime(self.file_path)
            if mtime == self._last_mtime:
                return
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            entries: Dict[str, UnknownProductEntry] = {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, dict):
                        entry = UnknownProductEntry.from_dict({**v, "barcode": k})
                        if entry.barcode:
                            entries[entry.barcode] = entry
            self._entries = entries
            self._last_mtime = mtime
        except Exception as e:
            print(f"[UnknownTracker] Warning: Failed to load '{self.file_path}': {e}")

    def save(self) -> None:
        parent = os.path.dirname(self.file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        payload = {b: e.to_dict() for b, e in sorted(self._entries.items())}
        tmp_path = self.file_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        os.replace(tmp_path, self.file_path)
        self._last_mtime = os.path.getmtime(self.file_path)

    def record_unknown(
        self,
        barcode: Optional[str],
        stock_code: Optional[str] = None,
        trendyol_name: Optional[str] = None,
        seller_id: Optional[str] = None,
        seller_name: Optional[str] = None,
        order_number: Optional[str] = None,
    ) -> UnknownProductEntry:
        """Record or increment occurrence of an uncatalogued product."""
        self.load()
        norm_b = normalize_identifier(barcode) or f"UNKNOWN_{stock_code or 'NO_ID'}"
        now_iso = datetime.now().isoformat(timespec="seconds")

        if norm_b in self._entries:
            entry = self._entries[norm_b]
            entry.occurrence_count += 1
            entry.last_seen = now_iso
            if stock_code and not entry.stock_code:
                entry.stock_code = stock_code
            if trendyol_name and not entry.trendyol_name:
                entry.trendyol_name = trendyol_name
            if seller_name and not entry.seller_name:
                entry.seller_name = seller_name
            if order_number:
                entry.sample_order_number = order_number
        else:
            entry = UnknownProductEntry(
                barcode=norm_b,
                stock_code=stock_code,
                trendyol_name=trendyol_name,
                seller_id=seller_id,
                seller_name=seller_name,
                first_seen=now_iso,
                last_seen=now_iso,
                occurrence_count=1,
                sample_order_number=order_number,
            )
            self._entries[norm_b] = entry

        self.save()
        return entry

    def remove(self, barcode: str) -> bool:
        """Remove a barcode once it has been promoted to products.json."""
        self.load()
        norm_b = normalize_identifier(barcode)
        if norm_b in self._entries:
            del self._entries[norm_b]
            self.save()
            return True
        return False

    def list_all(self) -> List[UnknownProductEntry]:
        self.load()
        return sorted(self._entries.values(), key=lambda e: e.occurrence_count, reverse=True)
