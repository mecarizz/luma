"""Order processing reporting and metrics aggregation engine.

Derives fulfillment statistics, daily throughput, seller distributions, and CSV
exports directly from persistent state (printed_packages.json) and unknown registry.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SummaryStats:
    total_packages: int = 0
    printed_count: int = 0
    outsourced_count: int = 0
    mixed_count: int = 0
    failed_count: int = 0
    baseline_count: int = 0
    unknown_products_count: int = 0
    by_seller: Dict[str, Dict[str, int]] = field(default_factory=dict)
    by_day: Dict[str, Dict[str, int]] = field(default_factory=dict)
    by_carrier: Dict[str, int] = field(default_factory=dict)


class ReportingEngine:
    def __init__(
        self,
        state_file: str = "printed_packages.json",
        unknown_file: str = "unknown_products.json",
    ):
        self.state_file = state_file
        self.unknown_file = unknown_file

    def _load_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_file):
            return {"packages": {}}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {"packages": {}}
        except Exception:
            return {"packages": {}}

    def _load_unknown_count(self) -> int:
        if not os.path.exists(self.unknown_file):
            return 0
        try:
            with open(self.unknown_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return len(data) if isinstance(data, dict) else 0
        except Exception:
            return 0

    def get_summary(self) -> SummaryStats:
        state = self._load_state()
        packages = state.get("packages", {})
        stats = SummaryStats(
            total_packages=len(packages),
            unknown_products_count=self._load_unknown_count(),
        )

        for pid, meta in packages.items():
            action = meta.get("action", "")
            kind = meta.get("kind", "")
            seller = str(meta.get("seller") or "unknown")
            carrier = meta.get("carrier") or "unspecified"
            ts = meta.get("at") or ""
            day = ts[:10] if len(ts) >= 10 else "unknown_date"

            # Counters
            if action == "baseline":
                stats.baseline_count += 1
            elif action == "switch_failed" or meta.get("print_status") == "failed":
                stats.failed_count += 1
            elif "printed" in action:
                stats.printed_count += 1
                if kind == "mixed":
                    stats.mixed_count += 1
            elif action == "outsourced":
                stats.outsourced_count += 1

            # Carrier
            stats.by_carrier[carrier] = stats.by_carrier.get(carrier, 0) + 1

            # Seller breakdown
            s_dict = stats.by_seller.setdefault(
                seller,
                {"total": 0, "printed": 0, "outsourced": 0, "mixed": 0, "failed": 0, "baseline": 0},
            )
            s_dict["total"] += 1
            if action == "baseline":
                s_dict["baseline"] += 1
            elif "switch_failed" in action:
                s_dict["failed"] += 1
            elif "printed" in action:
                s_dict["printed"] += 1
                if kind == "mixed":
                    s_dict["mixed"] += 1
            elif action == "outsourced":
                s_dict["outsourced"] += 1

            # Daily breakdown
            d_dict = stats.by_day.setdefault(
                day,
                {"total": 0, "printed": 0, "outsourced": 0, "mixed": 0, "failed": 0, "baseline": 0},
            )
            d_dict["total"] += 1
            if action == "baseline":
                d_dict["baseline"] += 1
            elif "switch_failed" in action:
                d_dict["failed"] += 1
            elif "printed" in action:
                d_dict["printed"] += 1
                if kind == "mixed":
                    d_dict["mixed"] += 1
            elif action == "outsourced":
                d_dict["outsourced"] += 1

        return stats

    def export_history_to_csv(self, out_path: str) -> int:
        """Export sanitized persistent package records to CSV with UTF-8 BOM."""
        state = self._load_state()
        packages = state.get("packages", {})

        fields = [
            "package_id",
            "order_number",
            "seller",
            "tracking_number",
            "carrier",
            "kind",
            "action",
            "print_status",
            "pdf_status",
            "last_error",
            "processed_at",
        ]

        count = 0
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for pid, meta in sorted(packages.items(), key=lambda x: x[1].get("at") or "", reverse=True):
                row = {
                    "package_id": pid,
                    "order_number": meta.get("orderNumber") or "",
                    "seller": meta.get("seller") or "",
                    "tracking_number": meta.get("tracking") or "",
                    "carrier": meta.get("carrier") or "",
                    "kind": meta.get("kind") or "",
                    "action": meta.get("action") or "",
                    "print_status": meta.get("print_status") or ("success" if "printed" in meta.get("action", "") else "skipped"),
                    "pdf_status": meta.get("pdf_status") or ("success" if meta.get("pdf") else "skipped"),
                    "last_error": meta.get("last_error") or "",
                    "processed_at": meta.get("at") or "",
                }
                writer.writerow(row)
                count += 1

        return count
