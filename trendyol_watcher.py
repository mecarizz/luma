#!/usr/bin/env python3
"""
Trendyol order watcher
----------------------
Runs forever (until Ctrl+C) and, for every NEW package that shows up:

  1. switches its cargo company to the seller's configured carrier (DHL / TEX) if it isn't set already
  2. re-fetches the package (the tracking number changes when the carrier changes)
  3. builds the label PDF with trendyol_labels.py and sends it to your thermal printer

Outsourced products: barcodes listed in outsourced_products.txt are NOT printed. Their label is saved as
outsourced_labels/<date>/<date>_<Customer>_<PRODUCT>.pdf instead (ready to send to your supplier).
If an order mixes outsourced and in-stock products it is printed AND saved (change with --mixed).

Each package is handled once; progress is kept in printed_packages.json.
Put trendyol_labels.py in the same folder. It uses the same .env file.

.env: one block per seller (see trendyol_labels.py), plus
    TRENDYOL_SELLER_ID_1=...   TRENDYOL_API_KEY_1=...   TRENDYOL_API_SECRET_1=...   TRENDYOL_SELLER_NAME_1=Loria   TRENDYOL_CARGO_PROVIDER_1=DHLECOMMP
    TRENDYOL_SELLER_ID_2=...   TRENDYOL_API_KEY_2=...   TRENDYOL_API_SECRET_2=...   TRENDYOL_SELLER_NAME_2=Other   TRENDYOL_CARGO_PROVIDER_2=TEX
    LABEL_SHIFT_Y_MM=44
    LABEL_SIZE=100x100
    PRINTER_NAME=Your Thermal Printer Name      # exactly as in Windows / CUPS
    SUMATRA_PATH=C:\\Users\\you\\AppData\\Local\\SumatraPDF\\SumatraPDF.exe   # Windows silent printing

First test (changes nothing, prints nothing):
    python trendyol_watcher.py --dry-run --once
Then, with a real new order:
    python trendyol_watcher.py --once
Normal use:
    python trendyol_watcher.py
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from types import SimpleNamespace

import requests

import trendyol_labels as tl      # also loads .env
from core.config import (
    DEFAULT_LABEL_SHIFT_Y_MM,
    DEFAULT_LABEL_SIZE,
    DEFAULT_PRINTER_NAME,
    DEFAULT_SUMATRA_PATH,
)
from core.logger import log, setup_logger
from core.paths import get_data_path

DHL_CODE = "DHLECOMMP"
TEX_CODE = "TEX"
STATE_FILE = str(get_data_path("printed_packages.json"))
OUT_DIR = str(get_data_path("labels_out"))
LOG_FILE = str(get_data_path("watcher.log"))
MAX_SWITCH_ATTEMPTS = 3           # per package
RETRY_AFTER_SECONDS = 300         # the API allows one carrier change per package per 5 minutes


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)
                if isinstance(state, dict):
                    state.setdefault("packages", {})
                    state.setdefault("sellers_seen", [])
                    state.setdefault("in_progress", {})
                    return state
        except Exception as e:
            log(f"Warning: Failed to load {STATE_FILE}: {e}")
    return {"packages": {}, "sellers_seen": [], "in_progress": {}}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def get_seller_cargo(seller):
    """Return target cargo provider code for a seller (default: DHLECOMMP for Seller 1, TEX for Seller 2)."""
    if isinstance(seller, dict):
        if seller.get("cargo"):
            return seller["cargo"]
        if seller.get("preferred_cargo"):
            return seller["preferred_cargo"]
    elif hasattr(seller, "preferred_cargo") and seller.preferred_cargo:
        return seller.preferred_cargo
    return "DHLECOMMP"


def is_target_cargo(pkg, target_cargo):
    """Check if package cargo matches the target cargo provider code."""
    provider_name = (pkg.get("cargoProviderName") or "").lower()
    provider_code = str(pkg.get("cargoProviderCode") or "").upper()
    target_code = str(target_cargo or "DHLECOMMP").upper()

    if provider_code == target_code:
        return True

    cargo_keywords = {
        "DHLECOMMP": ["dhl"],
        "TEX": ["trendyol express", "tex"],
        "YK": ["yurtiçi", "yurtici"],
        "ARAS": ["aras"],
        "MNG": ["mng"],
        "PTT": ["ptt"],
        "SURAT": ["sürat", "surat"],
        "SENDEO": ["sendeo"],
        "HOROZ": ["horoz"],
        "CEVA": ["ceva"],
    }
    keywords = cargo_keywords.get(target_code, [target_code.lower()])
    return any(kw in provider_name for kw in keywords)


def is_dhl(pkg):
    """Backward-compatible helper checking for DHL."""
    return is_target_cargo(pkg, "DHLECOMMP")


def pid_of(pkg):
    return str(pkg.get("shipmentPackageId"))


# --------------------------------------------------------------------------- #
# Trendyol: change cargo provider
# --------------------------------------------------------------------------- #
def seller_of(pkg):
    """The configured seller (with credentials) that a fetched package belongs to."""
    pkg_seller = pkg.get("_seller")
    if pkg_seller and isinstance(pkg_seller, dict) and "key" in pkg_seller and "secret" in pkg_seller:
        return pkg_seller
    sid = (pkg_seller or {}).get("id") if isinstance(pkg_seller, dict) else None
    try:
        configured = tl.get_sellers()
    except SystemExit:
        configured = []
    for sl in configured:
        if sl["id"] == sid:
            return sl
    if configured:
        return configured[0]
    return {
        "id": sid or "test_seller",
        "key": "",
        "secret": "",
        "name": (pkg_seller or {}).get("name", "") if isinstance(pkg_seller, dict) else "",
        "cargo": (pkg_seller or {}).get("cargo", "DHLECOMMP") if isinstance(pkg_seller, dict) else "DHLECOMMP",
    }


def switch_to_cargo(pkg_id, seller, target_cargo=None):
    if not target_cargo:
        target_cargo = get_seller_cargo(seller)
    sid, headers = tl.api_headers(seller)
    url = f"{tl.BASE_URL}/order/sellers/{sid}/shipment-packages/{pkg_id}/cargo-providers"
    for attempt in range(3):
        try:
            r = requests.put(url, headers={**headers, "Content-Type": "application/json"},
                             json={"cargoProvider": target_cargo}, timeout=30)
            if r.status_code == 200:
                return True, "ok"
            if r.status_code in (500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            request_id = r.headers.get("x-request-id") or r.headers.get("X-Request-ID")
            suffix = f" (request ID: {request_id})" if request_id else ""
            return False, f"HTTP {r.status_code}{suffix}"
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            return False, f"network error: {e}"
    return False, "Switch failed after retries"


def switch_to_dhl(pkg_id, seller):
    """Backward-compatible wrapper for switching cargo provider."""
    return switch_to_cargo(pkg_id, seller, "DHLECOMMP")


def refetch_as_cargo(pkg, opts, seller=None, tries=6):
    """After a switch, wait until the package reports target carrier, return the fresh package (new tracking no.)."""
    pid = pid_of(pkg)
    sl = seller or seller_of(pkg)
    target_cargo = get_seller_cargo(sl)
    for _ in range(tries):
        time.sleep(3)
        found = tl.fetch_packages(opts.status, 3, order_number=pkg.get("orderNumber"), seller=sl)
        matching = [p for p in found if pid_of(p) == pid]
        if not matching:
            # STRICT ID MATCH: Never fall back to other packages of the same order
            continue
        for p in matching:
            if is_target_cargo(p, target_cargo):
                return p
    return None


def refetch_as_dhl(pkg, opts, tries=6):
    """Backward-compatible wrapper."""
    return refetch_as_cargo(pkg, opts, tries=tries)


# --------------------------------------------------------------------------- #
# printing
# --------------------------------------------------------------------------- #
def send_to_printer(pdf_path, printer):
    pdf_path = os.path.abspath(pdf_path)
    try:
        if sys.platform.startswith("win"):
            sumatra = os.getenv("SUMATRA_PATH", DEFAULT_SUMATRA_PATH)
            if sumatra and os.path.exists(sumatra):
                target = ["-print-to", printer] if printer else ["-print-to-default"]
                cmd = [sumatra, *target, "-print-settings", "noscale", "-silent", pdf_path]
                return subprocess.run(cmd, timeout=60).returncode == 0
            log(f"PRINT ERROR: SumatraPDF not found at '{sumatra}'. Silent thermal printing requires SumatraPDF.exe.")
            return False
        cmd = ["lp"] + (["-d", printer] if printer else []) + [pdf_path]
        return subprocess.run(cmd, timeout=60).returncode == 0
    except subprocess.TimeoutExpired:
        log(f"PRINT ERROR: Printing timed out after 60s for {pdf_path}")
        return False
    except Exception as e:                           # noqa: BLE001
        log(f"PRINT ERROR: {e}")
        return False


def make_label_pdf(packages, opts):
    os.makedirs(OUT_DIR, exist_ok=True)
    sid = (packages[0].get("_seller") or {}).get("id", "x")      # keeps two sellers' batches apart
    path = os.path.join(OUT_DIR, f"batch_{datetime.now():%Y%m%d_%H%M%S}_{sid}.pdf")
    tl.build_pdf(packages, path, opts.label)
    return path


# --------------------------------------------------------------------------- #
# one polling cycle
# --------------------------------------------------------------------------- #
def poll_once(opts, state, attempts, seller, baseline_only=False, on_processed=None):
    tag = tl.seller_tag(seller)
    target_cargo = get_seller_cargo(seller)
    cargo_label = "TEX" if target_cargo == "TEX" else ("DHL" if target_cargo == "DHLECOMMP" else target_cargo)
    patterns = tl.load_outsourced(opts.outsourced_file)          # re-read each cycle: edits apply instantly
    log(
        f"[{tag}] Checking Trendyol orders: statuses={','.join(opts.status)} "
        f"lookback_hours={opts.lookback_hours}"
    )
    packages = tl.fetch_packages(opts.status, opts.lookback_hours / 24, seller=seller)
    log(f"[{tag}] Trendyol returned {len(packages)} package(s) for this poll.")
    seen = state["packages"]
    in_progress = state.setdefault("in_progress", {})
    new = [p for p in packages if pid_of(p) not in seen]
    log(f"[{tag}] {len(new)} package(s) are new to the local processed-order state.")

    if baseline_only:
        for p in new:
            seen[pid_of(p)] = {"orderNumber": p.get("orderNumber"), "action": "baseline"}
        if not opts.dry_run:
            save_state(state)
        log(f"[{tag}] First run for this seller: {len(new)} existing package(s) marked as already handled "
            "(not printed). Only orders arriving from now on will be processed.")
        return

    if not new:
        return
    log(f"[{tag}] {len(new)} new package(s) found")

    ready = []
    for p in new:
        pid, order = pid_of(p), p.get("orderNumber")
        name = (p.get("shipmentAddress") or {}).get("fullName", "?")
        carrier = p.get("cargoProviderName") or "?"

        kind, do_print, do_save = tl.route(p, patterns, opts.mixed)
        todo = " + ".join(x for x, on in (("print", do_print), (f"save PDF ({kind})", do_save)) if on)

        if is_target_cargo(p, target_cargo) or opts.no_switch or (kind == "outsourced" and opts.no_switch_outsourced):
            ready.append(p)
            continue

        if opts.dry_run:
            log(f"[dry-run] [{tag}] would switch order {order} ({name}) from '{carrier}' to {cargo_label}, then {todo}")
            continue

        pkg_prog = in_progress.setdefault(pid, {})
        retry_at = pkg_prog.get("retry_at", 0)
        if time.time() < retry_at:
            continue                                  # waiting out the 5-minute window

        current_attempts = pkg_prog.get("switch_attempts", 0) + 1
        pkg_prog["switch_attempts"] = current_attempts
        ok, msg = switch_to_cargo(pid, seller, target_cargo)
        if not ok:
            pkg_prog["retry_at"] = time.time() + RETRY_AFTER_SECONDS
            pkg_prog["last_error"] = msg
            save_state(state)
            log(f"[{tag}] SWITCH FAILED order {order} ({name}), attempt {current_attempts}/{MAX_SWITCH_ATTEMPTS}: {msg}")
            if current_attempts >= MAX_SWITCH_ATTEMPTS:
                if opts.print_on_fail:
                    log(f"  giving up -> printing the ORIGINAL ({carrier}) label for order {order}")
                    ready.append(p)
                else:
                    log(f"  giving up on order {order}. Handle it manually; marked as failed.")
                    seen[pid] = {
                        "orderNumber": order,
                        "action": "switch_failed",
                        "seller": (p.get("_seller") or {}).get("id"),
                        "carrier": carrier,
                        "last_error": msg,
                        "at": datetime.now().isoformat(timespec="seconds"),
                    }
                    in_progress.pop(pid, None)
                    save_state(state)
            continue

        fresh = refetch_as_cargo(p, opts, seller=seller)
        if fresh is None:
            pkg_prog["last_error"] = f"Carrier switch accepted, but package does not report {cargo_label} yet"
            save_state(state)
            log(f"[{tag}] Switched order {order} but it does not report {cargo_label} yet; will check again next cycle")
            continue
        log(f"[{tag}] Order {order} ({name}): {carrier} -> {fresh.get('cargoProviderName')}")
        ready.append(fresh)

    if opts.dry_run:
        for p in ready:
            kind, do_print, do_save = tl.route(p, patterns, opts.mixed)
            todo = " + ".join(x for x, on in (("print", do_print), (f"save PDF ({kind})", do_save)) if on)
            log(f"[dry-run] would {todo}: order {p.get('orderNumber')} (already {p.get('cargoProviderName')})")
        return

    if not ready:
        return

    # ---- decide per package: print, save as outsourced PDF, or both (mixed) ----
    plan = {}
    for p in ready:
        plan[pid_of(p)] = tl.route(p, patterns, opts.mixed)
    to_print = [p for p in ready if plan[pid_of(p)][1]]
    to_save = [p for p in ready if plan[pid_of(p)][2]]

    # outsourced PDFs first (they don't need the printer)
    for p in to_save:
        pid, kind = pid_of(p), plan[pid_of(p)][0]
        pkg_prog = in_progress.setdefault(pid, {})
        saved_path = pkg_prog.get("saved_pdf")
        if saved_path and os.path.exists(saved_path):
            continue
        who = (p.get("shipmentAddress") or {}).get("fullName", "?")
        try:
            saved_path = tl.save_outsourced_pdf(p, opts.label, kind)
            pkg_prog["saved_pdf"] = saved_path
            save_state(state)
        except OSError as e:
            log(f"[{tag}] SAVE FAILED order {p.get('orderNumber')} ({who}): {e}")
            continue
        if kind == "mixed":
            log(f"[{tag}] MIXED order {p.get('orderNumber')} ({who}): has outsourced AND in-stock items "
                f"- saved a copy: {saved_path}  (check this one by hand)")
        else:
            log(f"[{tag}] OUTSOURCED order {p.get('orderNumber')} ({who}): not printed, saved: {saved_path}")

    printed_ok = set()
    if to_print:
        pdf = make_label_pdf(to_print, opts)
        if opts.no_print or send_to_printer(pdf, opts.printer):
            printed_ok = {pid_of(p) for p in to_print}
            log(f"{'Saved' if opts.no_print else 'Printed'} {len(to_print)} label(s): {pdf}")
        else:
            log(f"PRINT FAILED for {pdf}. Those packages stay pending and will be retried next cycle.")

    for p in ready:
        pid = pid_of(p)
        kind, do_print, do_save = plan[pid]
        pkg_prog = in_progress.get(pid, {})
        has_saved_pdf = bool(pkg_prog.get("saved_pdf") and os.path.exists(pkg_prog["saved_pdf"]))
        if (do_print and pid not in printed_ok) or (do_save and not has_saved_pdf):
            continue                                   # something failed -> retry next cycle
        action = ("outsourced" if not do_print else
                  "printed+saved" if do_save else
                  "saved" if opts.no_print else "printed")
        seen[pid] = {
            "orderNumber": p.get("orderNumber"),
            "seller": (p.get("_seller") or {}).get("id"),
            "tracking": str(p.get("cargoTrackingNumber")),
            "carrier": p.get("cargoProviderName"),
            "kind": kind,
            "action": action,
            "pdf": pkg_prog.get("saved_pdf"),
            "print_status": "success" if do_print else "skipped",
            "pdf_status": "success" if do_save else "skipped",
            "last_error": None,
            "retry_count": pkg_prog.get("switch_attempts", 0),
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        in_progress.pop(pid, None)
    save_state(state)
    if on_processed:
        for p in ready:
            pid = pid_of(p)
            if pid in seen:
                on_processed(
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    tag,
                    str(p.get("orderNumber") or ""),
                    str(p.get("cargoProviderName") or ""),
                    str(seen[pid].get("action") or "Processed"),
                )


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", nargs="+", default=["Created", "Picking"],
                    help="statuses to watch (default: Created Picking)")
    ap.add_argument("--interval", type=int, default=30, help="seconds between checks (default 30)")
    ap.add_argument("--lookback-hours", type=float, default=48, help="how far back each check looks")
    ap.add_argument("--no-switch", action="store_true", help="don't change the cargo company")
    ap.add_argument("--no-print", action="store_true", help="only save PDFs in labels_out/")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, change/print nothing")
    ap.add_argument("--once", action="store_true", help="run a single check and exit")
    ap.add_argument("--outsourced-file", default=tl.DEFAULT_OUTSOURCED_FILE,
                    help="barcodes you don't stock (default outsourced_products.txt or OUTSOURCED_FILE in .env)")
    ap.add_argument("--mixed", choices=["both", "print", "save"], default="both",
                    help="orders mixing outsourced and in-stock items: print + save copy (default) | print | save")
    ap.add_argument("--no-switch-outsourced", action="store_true",
                    help="don't change the carrier for fully outsourced orders")
    ap.add_argument("--print-existing", action="store_true",
                    help="on the very first run also process packages that already exist")
    ap.add_argument("--print-on-fail", action="store_true",
                    help="if switching carrier keeps failing, print the original label anyway")
    ap.add_argument("--printer", default=os.getenv("PRINTER_NAME", DEFAULT_PRINTER_NAME),
                    help="printer name (default: system default printer or PRINTER_NAME in .env)")
    # label look - same options as trendyol_labels.py
    ap.add_argument("--size", default=os.getenv("LABEL_SIZE", DEFAULT_LABEL_SIZE),
                    help=f"label dimensions WxH (default: {DEFAULT_LABEL_SIZE})")
    ap.add_argument("--shift-y", type=float, default=float(os.getenv("LABEL_SHIFT_Y_MM", DEFAULT_LABEL_SHIFT_Y_MM)),
                    help=f"top vertical offset mm (default: {DEFAULT_LABEL_SHIFT_Y_MM})")
    ap.add_argument("--name-words", type=int, default=1)
    ap.add_argument("--overrides", help="JSON file {barcode_or_stockCode: 'Short Name'}")
    ap.add_argument("--catalog", default=os.getenv("PRODUCTS_FILE", str(get_data_path("products.json"))),
                    help="path to products.json catalog")
    ap.add_argument("--no-catalog", action="store_true",
                    help="disable catalog lookup and use legacy first-word extraction")
    ap.add_argument("--unknown-file", default=os.getenv("UNKNOWN_PRODUCTS_FILE", str(get_data_path("unknown_products.json"))),
                    help="path to unknown_products.json")
    ap.add_argument("--log-file", default=os.getenv("LOG_FILE", str(get_data_path("watcher.log"))),
                    help="path to rotating watcher log file")
    ap.add_argument("--address", action="store_true")
    ap.add_argument("--footer", action="store_true")
    ap.add_argument("--stamp", choices=["both", "order", "print", "none"], default="both",
                    help="date/time on the label: SİP (order), BAS (print), both, none")
    ap.add_argument("--no-seller", dest="show_seller", action="store_false", help="hide seller name on the label")
    ap.add_argument("--font")
    opts = ap.parse_args()

    setup_logger(opts.log_file)
    w, h = (float(x) for x in opts.size.lower().split("x"))
    overrides = json.load(open(opts.overrides, encoding="utf-8")) if opts.overrides else {}
    opts.label = SimpleNamespace(w=w, h=h, shift_y=opts.shift_y, address=opts.address,
                                 footer=opts.footer, name_words=opts.name_words, overrides=overrides,
                                 stamp=opts.stamp, show_seller=opts.show_seller,
                                 catalog=opts.catalog, no_catalog=opts.no_catalog,
                                 unknown_file=opts.unknown_file)
    tl.register_font(opts.font)

    sellers = tl.get_sellers()
    log(f"Watcher started. statuses={opts.status} interval={opts.interval}s "
        f"switch_cargo={not opts.no_switch} dry_run={opts.dry_run} printer={opts.printer or '(default)'}")
    for n, sl in enumerate(sellers, 1):
        target_cargo = get_seller_cargo(sl)
        log(f"  seller {n}: id={sl['id']} name={sl['name'] or '(none - label shows the id)'} cargo={target_cargo}")

    state = load_state()
    if state is None:
        state = {"packages": {}, "sellers_seen": []}
    elif "sellers_seen" not in state:
        # state file from the single-seller version: it belongs to the first seller
        state["sellers_seen"] = [sellers[0]["id"]]
    attempts = {}
    first_cycle = True

    try:
        while True:
            failed = 0
            for sl in sellers:
                is_new_seller = sl["id"] not in state["sellers_seen"]
                baseline = is_new_seller and not opts.print_existing
                try:
                    poll_once(opts, state, attempts, sl, baseline_only=baseline)
                    if is_new_seller and not opts.dry_run:
                        state["sellers_seen"].append(sl["id"])
                        save_state(state)
                except SystemExit as e:              # auth/API problem for THIS seller only
                    failed += 1
                    log(f"[{tl.seller_tag(sl)}] SELLER ERROR: {e}")
                except Exception as e:               # noqa: BLE001  network blips etc. -> keep running
                    log(f"[{tl.seller_tag(sl)}] ERROR (will retry): {type(e).__name__}: {e}")
            if first_cycle and failed == len(sellers):
                log("STOPPED: every seller failed on the first check. Fix the credentials and run again.")
                sys.exit(1)
            first_cycle = False
            if opts.once:
                break
            time.sleep(opts.interval)
    except KeyboardInterrupt:
        log("Watcher stopped by user.")


if __name__ == "__main__":
    main()