#!/usr/bin/env python3
"""Product Catalog Management CLI.

Provides command-line operations to list, search, add, edit, delete, import,
export, and triage unknown products discovered during order processing.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import List, Optional

from core.catalog import ProductCatalog, ProductItem, normalize_identifier
from core.config import get_config
from core.unknown_tracker import UnknownProductTracker


def print_table(headers: List[str], rows: List[List[str]]) -> None:
    """Print an aligned ASCII table."""
    if not rows:
        print("(No entries found)")
        return
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], len(str(cell)))

    # Format header
    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    print(header_line)
    print(sep_line)
    for row in rows:
        line = " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        print(line)


def cmd_list(catalog: ProductCatalog, args: argparse.Namespace) -> None:
    prods = catalog.list_all()
    if args.seller:
        s_filter = args.seller.strip().lower()
        prods = [p for p in prods if (p.seller or "").strip().lower() == s_filter]
    if args.category:
        c_filter = args.category.strip().lower()
        prods = [p for p in prods if (p.category or "").strip().lower() == c_filter]

    headers = ["BARCODE", "STOCK CODE", "DISPLAY NAME", "SIZE TYPE", "SELLER", "CATEGORY"]
    rows = [
        [
            p.barcode,
            p.stock_code or "-",
            p.display_name,
            p.size_type or "-",
            p.seller or "-",
            p.category or "-",
        ]
        for p in prods
    ]
    print(f"\n=== PRODUCT CATALOG ({len(prods)} items) ===")
    print_table(headers, rows)


def cmd_search(catalog: ProductCatalog, args: argparse.Namespace) -> None:
    query = normalize_identifier(args.query)
    prods = catalog.list_all()
    hits: List[ProductItem] = []
    for p in prods:
        b = normalize_identifier(p.barcode)
        s = normalize_identifier(p.stock_code)
        n = normalize_identifier(p.display_name)
        if query in b or query in s or query in n:
            hits.append(p)

    headers = ["BARCODE", "STOCK CODE", "DISPLAY NAME", "SIZE TYPE", "SELLER"]
    rows = [
        [p.barcode, p.stock_code or "-", p.display_name, p.size_type or "-", p.seller or "-"]
        for p in hits
    ]
    print(f"\nSearch results for '{args.query}' ({len(hits)} match(es)):")
    print_table(headers, rows)


def cmd_add(catalog: ProductCatalog, args: argparse.Namespace) -> None:
    norm_b = normalize_identifier(args.barcode)
    if not norm_b:
        sys.exit("Error: --barcode cannot be empty.")
    if not args.name:
        sys.exit("Error: --name is required.")

    existing = catalog.get_by_barcode(norm_b)
    if existing:
        sys.exit(f"Error: Barcode '{norm_b}' already exists in catalog as '{existing.display_name}'. Use 'edit' to update.")

    stype = args.size_type.upper().strip() if args.size_type else None
    if stype and stype not in ("ÇİFT", "TEK"):
        sys.exit("Error: --size-type must be 'ÇİFT' or 'TEK' (or omitted).")

    item = ProductItem(
        barcode=norm_b,
        display_name=args.name.strip(),
        stock_code=normalize_identifier(args.stock_code) if args.stock_code else None,
        seller=args.seller.strip() if args.seller else None,
        category=args.category.strip() if args.category else None,
        product_type=args.type.strip() if args.type else None,
        size_type=stype,
        color=args.color.strip() if args.color else None,
        size=args.size.strip() if args.size else None,
        notes=args.notes.strip() if args.notes else None,
    )
    catalog.add_or_update(item)
    print(f"Added product '{norm_b}' ({item.display_name}) to catalog.")


def cmd_edit(catalog: ProductCatalog, args: argparse.Namespace) -> None:
    norm_b = normalize_identifier(args.barcode)
    item = catalog.get_by_barcode(norm_b)
    if not item:
        sys.exit(f"Error: Product with barcode '{norm_b}' not found.")

    if args.name:
        item.display_name = args.name.strip()
    if args.stock_code is not None:
        item.stock_code = normalize_identifier(args.stock_code) if args.stock_code else None
    if args.seller is not None:
        item.seller = args.seller.strip() if args.seller else None
    if args.category is not None:
        item.category = args.category.strip() if args.category else None
    if args.type is not None:
        item.product_type = args.type.strip() if args.type else None
    if args.size_type is not None:
        stype = args.size_type.upper().strip() if args.size_type else None
        if stype and stype not in ("ÇİFT", "TEK"):
            sys.exit("Error: --size-type must be 'ÇİFT' or 'TEK' (or empty).")
        item.size_type = stype
    if args.color is not None:
        item.color = args.color.strip() if args.color else None
    if args.size is not None:
        item.size = args.size.strip() if args.size else None
    if args.notes is not None:
        item.notes = args.notes.strip() if args.notes else None

    catalog.add_or_update(item)
    print(f"Updated product '{norm_b}' ({item.display_name}).")


def cmd_delete(catalog: ProductCatalog, args: argparse.Namespace) -> None:
    norm_b = normalize_identifier(args.barcode)
    item = catalog.get_by_barcode(norm_b)
    if not item:
        sys.exit(f"Error: Product with barcode '{norm_b}' not found.")

    if not args.yes:
        confirm = input(f"Are you sure you want to delete '{norm_b}' ({item.display_name})? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Deletion cancelled.")
            return

    if catalog.delete(norm_b):
        print(f"Successfully deleted '{norm_b}'.")
    else:
        print(f"Could not delete '{norm_b}'.")


def cmd_export(catalog: ProductCatalog, args: argparse.Namespace) -> None:
    prods = catalog.list_all()
    fields = [
        "barcode", "display_name", "stock_code", "seller",
        "category", "product_type", "size_type", "color", "size", "notes"
    ]
    with open(args.file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for p in prods:
            d = p.to_dict()
            writer.writerow({k: d.get(k) or "" for k in fields})
    print(f"Exported {len(prods)} product(s) to '{args.file}'.")


def cmd_import(catalog: ProductCatalog, args: argparse.Namespace) -> None:
    if not os.path.exists(args.file):
        sys.exit(f"Error: CSV file '{args.file}' does not exist.")

    imported, updated, skipped = 0, 0, 0
    with open(args.file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, 2):
            raw_b = row.get("barcode") or row.get("BARCODE")
            raw_n = row.get("display_name") or row.get("name") or row.get("NAME")
            if not raw_b or not raw_n:
                print(f"Row {row_num}: Missing barcode or name. Skipping.")
                skipped += 1
                continue

            b_norm = normalize_identifier(raw_b)
            existing = catalog.get_by_barcode(b_norm)

            stype = row.get("size_type") or row.get("sizeType")
            if stype:
                stype = str(stype).upper().strip()
                if stype not in ("ÇİFT", "TEK"):
                    stype = None

            item = ProductItem(
                barcode=b_norm,
                display_name=raw_n.strip(),
                stock_code=normalize_identifier(row.get("stock_code") or row.get("stockCode")),
                seller=(row.get("seller") or "").strip() or None,
                category=(row.get("category") or "").strip() or None,
                product_type=(row.get("product_type") or row.get("productType") or "").strip() or None,
                size_type=stype,
                color=(row.get("color") or "").strip() or None,
                size=(row.get("size") or "").strip() or None,
                notes=(row.get("notes") or "").strip() or None,
            )
            catalog.add_or_update(item)
            if existing:
                updated += 1
            else:
                imported += 1

    print(f"Import completed: {imported} added, {updated} updated, {skipped} skipped.")


def cmd_unknown(catalog: ProductCatalog, tracker: UnknownProductTracker, args: argparse.Namespace) -> None:
    entries = tracker.list_all()
    if not entries:
        print("No unknown products currently recorded. All order barcodes are recognized!")
        return

    if args.promote:
        norm_b = normalize_identifier(args.promote)
        target = next((e for e in entries if e.barcode == norm_b), None)
        if not target:
            sys.exit(f"Barcode '{norm_b}' not found in unknown products registry.")

        print(f"\nPromoting Unknown Product '{norm_b}':")
        print(f"  Trendyol Name: {target.trendyol_name}")
        print(f"  Stock Code   : {target.stock_code}")
        print(f"  Seller       : {target.seller_name}")

        name = input(f"Enter Display Name [{target.trendyol_name}]: ").strip() or target.trendyol_name
        stype = input("Enter Size Type (ÇİFT / TEK / none): ").strip().upper()
        if stype not in ("ÇİFT", "TEK"):
            stype = None

        new_item = ProductItem(
            barcode=norm_b,
            display_name=name or norm_b,
            stock_code=target.stock_code,
            seller=target.seller_name,
            size_type=stype,
        )
        catalog.add_or_update(new_item)
        tracker.remove(norm_b)
        print(f"Promoted '{norm_b}' to products.json and removed from unknown tracker.")
        return

    headers = ["BARCODE", "STOCK CODE", "COUNT", "SELLER", "SAMPLE ORDER", "TRENDYOL PRODUCT NAME"]
    rows = [
        [
            e.barcode,
            e.stock_code or "-",
            str(e.occurrence_count),
            e.seller_name or "-",
            e.sample_order_number or "-",
            (e.trendyol_name or "-")[:45],
        ]
        for e in entries
    ]
    print(f"\n=== UNKNOWN ORDER BARCODES ({len(entries)} items) ===")
    print("Promote to catalog using: python manage_products.py unknown --promote <BARCODE>\n")
    print_table(headers, rows)


def cmd_missing(catalog: ProductCatalog, args: argparse.Namespace) -> None:
    prods = catalog.list_all()
    missing_items = []
    for p in prods:
        issues = []
        if not p.stock_code:
            issues.append("missing stock_code")
        if not p.seller:
            issues.append("missing seller")
        if not p.category:
            issues.append("missing category")
        if issues:
            missing_items.append([p.barcode, p.display_name, ", ".join(issues)])

    print(f"\n=== PRODUCTS MISSING ESSENTIAL INFORMATION ({len(missing_items)} items) ===")
    print_table(["BARCODE", "DISPLAY NAME", "MISSING FIELDS"], missing_items)


def main() -> None:
    cfg = get_config()
    catalog = ProductCatalog(cfg.products_file)
    tracker = UnknownProductTracker(cfg.unknown_products_file)

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="List all catalog products")
    p_list.add_argument("--seller", help="Filter by seller name")
    p_list.add_argument("--category", help="Filter by category")

    # search
    p_search = sub.add_parser("search", help="Search catalog by barcode, stock code, or name")
    p_search.add_argument("query", help="Search term")

    # add
    p_add = sub.add_parser("add", help="Add a product to catalog")
    p_add.add_argument("--barcode", required=True, help="Product barcode (unique)")
    p_add.add_argument("--name", required=True, help="Display name on thermal label")
    p_add.add_argument("--stock-code", help="Stock code")
    p_add.add_argument("--seller", help="Seller name")
    p_add.add_argument("--category", help="Category (e.g. Nevresim, Kırlent)")
    p_add.add_argument("--type", help="Product type (e.g. Yatak Örtüsü)")
    p_add.add_argument("--size-type", choices=["ÇİFT", "TEK", "çift", "tek"], help="ÇİFT / TEK badge")
    p_add.add_argument("--color", help="Color")
    p_add.add_argument("--size", help="Size dimension")
    p_add.add_argument("--notes", help="Internal notes")

    # edit
    p_edit = sub.add_parser("edit", help="Edit an existing product")
    p_edit.add_argument("barcode", help="Barcode of product to edit")
    p_edit.add_argument("--name", help="Updated display name")
    p_edit.add_argument("--stock-code", help="Updated stock code")
    p_edit.add_argument("--seller", help="Updated seller")
    p_edit.add_argument("--category", help="Updated category")
    p_edit.add_argument("--type", help="Updated product type")
    p_edit.add_argument("--size-type", choices=["ÇİFT", "TEK", "çift", "tek"], help="ÇİFT / TEK badge")
    p_edit.add_argument("--color", help="Updated color")
    p_edit.add_argument("--size", help="Updated size")
    p_edit.add_argument("--notes", help="Updated notes")

    # delete
    p_del = sub.add_parser("delete", help="Delete a product from catalog")
    p_del.add_argument("barcode", help="Barcode of product to delete")
    p_del.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # export
    p_export = sub.add_parser("export", help="Export catalog to CSV")
    p_export.add_argument("file", help="Destination CSV path (e.g. products.csv)")

    # import
    p_import = sub.add_parser("import", help="Import products from CSV")
    p_import.add_argument("file", help="Source CSV path")

    # unknown
    p_unk = sub.add_parser("unknown", help="View or triage unknown barcodes discovered in orders")
    p_unk.add_argument("--promote", help="Promote specified barcode to catalog")

    # missing
    sub.add_parser("missing", help="Report products with missing essential details")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == "list":
        cmd_list(catalog, args)
    elif args.command == "search":
        cmd_search(catalog, args)
    elif args.command == "add":
        cmd_add(catalog, args)
    elif args.command == "edit":
        cmd_edit(catalog, args)
    elif args.command == "delete":
        cmd_delete(catalog, args)
    elif args.command == "export":
        cmd_export(catalog, args)
    elif args.command == "import":
        cmd_import(catalog, args)
    elif args.command == "unknown":
        cmd_unknown(catalog, tracker, args)
    elif args.command == "missing":
        cmd_missing(catalog, args)


if __name__ == "__main__":
    main()
