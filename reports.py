#!/usr/bin/env python3
"""Fulfillment and Order Processing Reporting CLI.

Displays aggregated statistics, throughput by seller, daily trends, and exports
audit reports directly from persistent application state.
"""
from __future__ import annotations

import argparse
import sys
from typing import List

from core.config import get_config
from core.reporting import ReportingEngine


def print_table(headers: List[str], rows: List[List[str]]) -> None:
    if not rows:
        print("(No records found)")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            if idx < len(widths):
                widths[idx] = max(widths[idx], len(str(cell)))

    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * widths[i] for i in range(len(headers)))
    print(header_line)
    print(sep_line)
    for row in rows:
        print(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def cmd_summary(engine: ReportingEngine) -> None:
    stats = engine.get_summary()
    print("\n" + "=" * 55)
    print("      TRENDYOL ORDER MANAGEMENT SUMMARY REPORT")
    print("=" * 55)
    print(f"Total Packages Handled    : {stats.total_packages}")
    print(f"  - Thermal Labels Printed: {stats.printed_count}")
    print(f"  - Outsourced Orders     : {stats.outsourced_count}")
    print(f"  - Mixed Orders          : {stats.mixed_count}")
    print(f"  - Baseline (Initial Run): {stats.baseline_count}")
    print(f"  - Failed Switches/Prints: {stats.failed_count}")
    print(f"Uncatalogued Barcodes Logged: {stats.unknown_products_count}")

    if stats.by_carrier:
        print("\n--- CARRIER BREAKDOWN ---")
        for carrier, count in sorted(stats.by_carrier.items(), key=lambda x: x[1], reverse=True):
            print(f"  * {carrier:<30}: {count} package(s)")
    print("=" * 55 + "\n")


def cmd_daily(engine: ReportingEngine) -> None:
    stats = engine.get_summary()
    headers = ["DATE", "TOTAL", "PRINTED", "OUTSOURCED", "MIXED", "FAILED", "BASELINE"]
    rows = []
    for day, metrics in sorted(stats.by_day.items(), reverse=True):
        rows.append([
            day,
            str(metrics["total"]),
            str(metrics["printed"]),
            str(metrics["outsourced"]),
            str(metrics["mixed"]),
            str(metrics["failed"]),
            str(metrics["baseline"]),
        ])
    print("\n=== DAILY PROCESSING THROUGHPUT ===")
    print_table(headers, rows)


def cmd_sellers(engine: ReportingEngine) -> None:
    stats = engine.get_summary()
    cfg = get_config()
    seller_names = {s.id: s.name for s in cfg.sellers}

    headers = ["SELLER ID", "NAME", "TOTAL", "PRINTED", "OUTSOURCED", "MIXED", "FAILED"]
    rows = []
    for sid, metrics in sorted(stats.by_seller.items(), key=lambda x: x[1]["total"], reverse=True):
        rows.append([
            sid,
            seller_names.get(sid) or "-",
            str(metrics["total"]),
            str(metrics["printed"]),
            str(metrics["outsourced"]),
            str(metrics["mixed"]),
            str(metrics["failed"]),
        ])
    print("\n=== PROCESSING BREAKDOWN BY SELLER ===")
    print_table(headers, rows)


def cmd_export(engine: ReportingEngine, out_path: str) -> None:
    count = engine.export_history_to_csv(out_path)
    print(f"Successfully exported {count} order record(s) to '{out_path}'.")


def main() -> None:
    cfg = get_config()
    engine = ReportingEngine(cfg.state_file, cfg.unknown_products_file)

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("summary", help="Overall fulfillment metrics summary")
    sub.add_parser("daily", help="Daily throughput breakdown")
    sub.add_parser("sellers", help="Breakdown by seller account")
    p_exp = sub.add_parser("export", help="Export order history to CSV")
    p_exp.add_argument("file", help="Destination CSV file path (e.g. order_history.csv)")

    args = parser.parse_args()
    if not args.command or args.command == "summary":
        cmd_summary(engine)
    elif args.command == "daily":
        cmd_daily(engine)
    elif args.command == "sellers":
        cmd_sellers(engine)
    elif args.command == "export":
        cmd_export(engine, args.file)


if __name__ == "__main__":
    main()
