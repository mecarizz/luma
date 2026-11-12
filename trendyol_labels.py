#!/usr/bin/env python3
"""
Trendyol -> thermal label generator
-----------------------------------
Pulls order packages from the Trendyol seller API and builds ONE multi-page PDF
with one clean label per package:

    [ cargo barcode + number ]
    [ customer name          ]
    [ SHORT PRODUCT NAME  xN ]   <- first word of productName ("Loria")
    [ Renk / Beden / Stok Kodu / Barkod ]

All of those fields come straight from the order lines in getShipmentPackages
(productName, productColor, productSize, stockCode, barcode), so no scraping
of product pages is needed.

Setup
    pip install reportlab requests
    pip install python-dotenv   (optional, for .env)
    .env, one block per seller (add as many as you like: _1, _2, _3 ...):
        TRENDYOL_SELLER_ID_1=674974
        TRENDYOL_API_KEY_1=...
        TRENDYOL_API_SECRET_1=...
        TRENDYOL_SELLER_NAME_1=Loria          # optional friendly name shown on the label
        TRENDYOL_SELLER_ID_2=...
    (The old single-seller names TRENDYOL_SELLER_ID / _API_KEY / _API_SECRET still work.)
    Optional: SELLER_NAMES=674974:Loria,123456:Ayla   # names by seller id, if you prefer one line

Examples
    python trendyol_labels.py                         # all Picking (İşleme Alınanlar) packages, last 7 days
    python trendyol_labels.py --days 3 --sort product
    python trendyol_labels.py --order 10654411111     # a single order
    python trendyol_labels.py --status Created Picking
    python trendyol_labels.py --input orders.json     # offline / testing
    python trendyol_labels.py --size 100x100 --address --footer
"""
import argparse
import fnmatch
import re
import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()          # reads .env from the current folder
except ImportError:
    pass                   # fine if you set real environment variables instead

from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from core.catalog import ProductCatalog
from core.classifier import OutsourcedClassifier
from core.paths import get_data_path
from core.unknown_tracker import UnknownProductTracker

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
BASE_URL = os.getenv("TRENDYOL_BASE_URL", "https://apigw.trendyol.com/integration")
MAX_WINDOW_DAYS = 14          # docs: startDate/endDate range max two weeks
PAGE_SIZE = 200               # docs: max size per request
MAX_PAGE_INDEX = 49           # docs: only first 10,000 records reachable (page 0..49)

FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
FONT_NAME = "LabelBold"


def register_font(path=None):
    for p in ([path] if path else []) + FONT_CANDIDATES:
        if p and os.path.exists(p):
            pdfmetrics.registerFont(TTFont(FONT_NAME, p))
            return
    sys.exit("No Turkish-capable bold TTF font found. Pass one with --font path/to/font.ttf")


# --------------------------------------------------------------------------- #
# Turkish-aware text helpers
# --------------------------------------------------------------------------- #
TR_TZ = timezone(timedelta(hours=3))      # Turkey: UTC+3 all year


def fmt_ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TR_TZ).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return ""


def seller_label(pkg):
    sl = pkg.get("_seller") or {}
    return (sl.get("name") or sl.get("id") or "").upper()


def tr_upper(s):
    return (s or "").replace("i", "İ").replace("ı", "I").upper()


def tr_lower(s):
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def pack_type(line):
    """Detect bed-size type from productName -> 'ÇİFT', 'TEK' or None.

    Looks for 'çift kişilik' / 'tek kişilik' (also 'çift kişi', 'tek kişi', 'çiftkişilik').
    A bare 'Tek' is ignored on purpose: 'Tek Ebat' (= one size) appears in many names.
    """
    import re
    name = tr_lower(line.get("productName") or "")
    m = re.search(r"\b(çift|tek)\s*kişi", name)
    if m:
        return "ÇİFT" if m.group(1) == "çift" else "TEK"
    if re.search(r"\bçift\b", name):      # 'çift' alone is unambiguous enough
        return "ÇİFT"
    return None


def short_product_name(line, words=1, overrides=None):
    """'Loria Peluş Çift Kişilik ...' -> 'LORIA'. Overrides keyed by barcode/stockCode."""
    overrides = overrides or {}
    for key in (line.get("barcode"), line.get("stockCode")):
        if key and key in overrides:
            return overrides[key].upper()
    name = (line.get("productName") or "").strip()
    # plain upper(): brand names are Latin, so "Loria" -> "LORIA" (not "LORİA")
    return " ".join(name.split()[:words]).upper() or "?"


_CATALOG = None
_TRACKER = None


def get_catalog(path=None):
    global _CATALOG
    if _CATALOG is None or path:
        cat_path = path or os.getenv("PRODUCTS_FILE", str(get_data_path("products.json")))
        _CATALOG = ProductCatalog(cat_path)
    return _CATALOG


def get_tracker(path=None):
    global _TRACKER
    if _TRACKER is None or path:
        trk_path = path or os.getenv("UNKNOWN_PRODUCTS_FILE", str(get_data_path("unknown_products.json")))
        _TRACKER = UnknownProductTracker(trk_path)
    return _TRACKER


def resolve_line_product(ln, pkg=None, opts=None):
    """Resolve display name and size type (ÇİFT/TEK) using catalog with deterministic fallbacks."""
    if opts and getattr(opts, "no_catalog", False):
        return short_product_name(ln, getattr(opts, "name_words", 1), getattr(opts, "overrides", {})), pack_type(ln)

    catalog = getattr(opts, "catalog_obj", None) or get_catalog(getattr(opts, "catalog", None))
    overrides = getattr(opts, "overrides", {}) or {}
    words = getattr(opts, "name_words", 1)
    seller_name = (pkg.get("_seller") or {}).get("name") if pkg else None

    if catalog:
        resolved_name, size_type, source = catalog.resolve(
            barcode=ln.get("barcode"),
            stock_code=ln.get("stockCode"),
            product_name=ln.get("productName"),
            overrides=overrides,
            seller=seller_name,
            name_words=words,
        )
        if source == "trendyol_fallback" and ln.get("barcode"):
            tracker = get_tracker(getattr(opts, "unknown_file", None))
            if tracker:
                tracker.record_unknown(
                    barcode=ln.get("barcode"),
                    stock_code=ln.get("stockCode"),
                    trendyol_name=ln.get("productName"),
                    seller_id=(pkg.get("_seller") or {}).get("id") if pkg else None,
                    seller_name=seller_name,
                    order_number=pkg.get("orderNumber") if pkg else None,
                )
        return resolved_name, size_type

    return short_product_name(ln, words, overrides), pack_type(ln)


# --------------------------------------------------------------------------- #
# Trendyol API
# --------------------------------------------------------------------------- #
_SELLERS = None


def set_sellers(sellers):
    """Set explicit seller profiles for in-process callers such as the desktop app."""
    global _SELLERS
    normalized = []
    for seller in sellers:
        item = {
            "id": str(seller.get("id") or "").strip(),
            "key": str(seller.get("key") or "").strip(),
            "secret": str(seller.get("secret") or "").strip(),
            "name": str(seller.get("name") or "").strip(),
            "cargo": str(seller.get("cargo") or "DHLECOMMP").strip(),
        }
        if not item["id"].isdigit():
            raise ValueError(f"Seller ID '{item['id']}' must contain digits only.")
        if not item["key"] or not item["secret"]:
            raise ValueError(f"Seller {item['id']} must have an API key and API secret.")
        normalized.append(item)

    ids = [seller["id"] for seller in normalized]
    if len(set(ids)) != len(ids):
        raise ValueError("Seller IDs must be unique.")
    _SELLERS = normalized


def get_sellers():
    """All configured sellers: [{'id','key','secret','name','cargo'}, ...] (first = seller 1)."""
    global _SELLERS
    if _SELLERS is not None:
        return _SELLERS
    names_map = {}
    for part in (os.getenv("SELLER_NAMES") or "").replace(";", ",").split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            names_map[k.strip()] = v.strip()

    sellers = []
    for i in range(1, 21):
        sid = os.getenv(f"TRENDYOL_SELLER_ID_{i}")
        key = os.getenv(f"TRENDYOL_API_KEY_{i}")
        secret = os.getenv(f"TRENDYOL_API_SECRET_{i}")
        cargo = os.getenv(f"TRENDYOL_CARGO_PROVIDER_{i}")
        if not (sid or key or secret):
            continue
        if not (sid and key and secret):
            sys.exit(f"Seller {i}: set TRENDYOL_SELLER_ID_{i}, TRENDYOL_API_KEY_{i} and "
                     f"TRENDYOL_API_SECRET_{i} (one of them is missing in .env).")
        name = os.getenv(f"TRENDYOL_SELLER_NAME_{i}") or names_map.get(sid.strip()) or ""
        # Default seller 1 to DHLECOMMP and seller 2 to TEX if not set in .env
        if not cargo:
            cargo = "TEX" if i == 2 else "DHLECOMMP"
        sellers.append({
            "id": sid.strip(),
            "key": key.strip(),
            "secret": secret.strip(),
            "name": name.strip(),
            "cargo": cargo.strip(),
        })

    if not sellers:                                   # legacy single-seller variables
        sid = os.getenv("TRENDYOL_SELLER_ID")
        key = os.getenv("TRENDYOL_API_KEY")
        secret = os.getenv("TRENDYOL_API_SECRET")
        cargo = os.getenv("TRENDYOL_CARGO_PROVIDER") or "DHLECOMMP"
        if not (sid and key and secret):
            sys.exit("No seller configured. In .env set TRENDYOL_SELLER_ID_1, TRENDYOL_API_KEY_1 and "
                     "TRENDYOL_API_SECRET_1 (and _2, _3 ... for more sellers).")
        name = os.getenv("TRENDYOL_SELLER_NAME") or names_map.get(sid.strip()) or ""
        sellers.append({
            "id": sid.strip(),
            "key": key.strip(),
            "secret": secret.strip(),
            "name": name.strip(),
            "cargo": cargo.strip(),
        })

    ids = [x["id"] for x in sellers]
    if len(set(ids)) != len(ids):
        sys.exit("The same seller id appears twice in .env.")
    _SELLERS = sellers
    return _SELLERS


def select_sellers(wanted):
    """--seller 674974 / --seller loria : restrict to matching sellers."""
    global _SELLERS
    allx = get_sellers()
    w = wanted.strip().lower()
    chosen = [x for x in allx if x["id"] == wanted.strip() or (x["name"] and w in x["name"].lower())]
    if not chosen:
        sys.exit(f"No configured seller matches '{wanted}'. Configured: "
                 + ", ".join(f"{x['id']} ({x['name'] or 'no name'})" for x in allx))
    _SELLERS = chosen


def seller_tag(seller):
    return seller["name"] or seller["id"]


def api_headers(seller=None):
    seller = seller or get_sellers()[0]
    sid, key, secret = seller["id"], seller["key"], seller["secret"]
    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    return sid, {
        "Authorization": f"Basic {token}",
        # Required, otherwise Trendyol answers 403
        "User-Agent": f"{sid} - SelfIntegration",
        "Accept": "application/json",
    }


VERBOSE = False
USE_LEGACY = False      # --legacy: use the deprecated /orders path instead of /v2/orders


def orders_url(sid):
    return f"{BASE_URL}/order/sellers/{sid}/" + ("orders" if USE_LEGACY else "v2/orders")


def _get(url, headers, params, retries=5):
    import requests
    for attempt in range(retries):
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if VERBOSE:
            print(f"  GET {r.url}\n  -> HTTP {r.status_code}, {len(r.content)} bytes")
        if r.status_code == 429:               # rate limited -> back off
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (401, 403):
            sys.exit(f"{r.status_code} from Trendyol: check API key/secret and the User-Agent. {r.text[:200]}")
        r.raise_for_status()
        return r.json()
    sys.exit("Still rate limited (429) after retries.")


def fetch_packages(statuses, days=7, order_number=None, seller=None):
    """Packages of one seller, or of ALL configured sellers when seller is None."""
    if seller is None:
        out = []
        for sl in get_sellers():
            out.extend(fetch_packages(statuses, days, order_number, seller=sl))
        return out

    sid, headers = api_headers(seller)
    url = orders_url(sid)
    packages, seen = [], set()

    end = datetime.now()
    start = end - timedelta(days=days)
    windows = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=MAX_WINDOW_DAYS), end)
        windows.append((cur, nxt))
        cur = nxt

    for status in statuses:
        for w_start, w_end in windows:
            page = 0
            while page <= MAX_PAGE_INDEX:
                params = {
                    "status": status,
                    "startDate": int(w_start.timestamp() * 1000),
                    "endDate": int(w_end.timestamp() * 1000),
                    "orderByField": "PackageLastModifiedDate",
                    "orderByDirection": "ASC",
                    "size": PAGE_SIZE,
                    "page": page,
                }
                if order_number:
                    params["orderNumber"] = order_number
                data = _get(url, headers, params)
                if VERBOSE:
                    print(f"  [{status}] page {page}: totalElements={data.get('totalElements')}, "
                          f"returned={len(data.get('content', []))}")
                for p in data.get("content", []):
                    pid = p.get("shipmentPackageId")
                    if pid not in seen:
                        seen.add(pid)
                        p["_seller"] = {"id": seller["id"], "name": seller["name"], "cargo": seller.get("cargo", "DHLECOMMP")}
                        packages.append(p)
                if page + 1 >= data.get("totalPages", 1):
                    break
                page += 1
    return packages



# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
ALL_STATUSES = ["Created", "Picking", "Invoiced", "Shipped", "Delivered", "Cancelled",
                "UnSupplied", "Returned", "UnDelivered", "Awaiting", "Verified"]


def _diagnose_one(seller, days):
    import requests
    print("=== 1. Credentials ===")
    sid, headers = api_headers(seller)
    key, secret = seller["key"], seller["secret"]
    print(f"name     : {seller['name'] or '(none set - label will show the id)'}")
    print(f"sellerId : {sid}")
    print(f"apiKey   : {key[:4]}...{key[-3:]} (len {len(key)})")
    print(f"apiSecret: len {len(secret)}")
    for name, val in (("TRENDYOL_SELLER_ID", sid), ("TRENDYOL_API_KEY", key), ("TRENDYOL_API_SECRET", secret)):
        if val != val.strip() or val[:1] in "\"'" or val[-1:] in "\"'":
            print(f"  !! {name} has stray spaces or quotes in .env - remove them")
    if not sid.isdigit():
        print("  !! sellerId should be digits only (the 'Satici ID' / cari ID, not the API key)")
    print(f"User-Agent: {headers['User-Agent']}")
    print(f"Base URL  : {BASE_URL}")

    now = datetime.now()
    start = now - timedelta(days=min(days, MAX_WINDOW_DAYS))
    base_params = {
        "startDate": int(start.timestamp() * 1000),
        "endDate": int(now.timestamp() * 1000),
        "size": 5,
        "orderByField": "PackageLastModifiedDate",
        "orderByDirection": "DESC",
    }

    def call(label, path, params):
        url = f"{BASE_URL}/order/sellers/{sid}/{path}"
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"  {label}: NETWORK ERROR {e}")
            return None
        try:
            body = r.json()
        except ValueError:
            body = None
        total = body.get("totalElements") if isinstance(body, dict) else None
        print(f"  {label}: HTTP {r.status_code}" + (f", totalElements={total}" if total is not None else ""))
        if r.status_code != 200:
            print(f"     body: {r.text[:300]}")
        return r.status_code, body

    print(f"\n=== 2. Auth + endpoint (last {min(days, MAX_WINDOW_DAYS)} days, no status filter) ===")
    res = call("v2/orders    ", "v2/orders", base_params)
    res_legacy = call("orders (legacy)", "orders", base_params)
    for r, name in ((res, "v2"), (res_legacy, "legacy")):
        if r and r[0] in (401, 403):
            print(f"  -> {name}: {r[0]} = auth problem. 401 = wrong key/secret/sellerId; "
                  "403 = missing/invalid User-Agent or blocked IP.")
    if not any(r and r[0] == 200 for r in (res, res_legacy)):
        print("\nNo endpoint answered 200, so the problem is credentials/network, not 'no orders'.")
        return

    body = res[1] if res and res[0] == 200 else (res_legacy[1] if res_legacy else None)
    sample = ((body or {}).get("content") or [None])[0]
    if sample:
        keys = sorted(sample.keys())
        print("\n=== 2b. What an order package contains ===")
        print("  fields:", ", ".join(keys))
        name_keys = [k for k in keys if "seller" in k.lower() or "supplier" in k.lower() or "merchant" in k.lower()
                     or "store" in k.lower()]
        print("  seller/store-like fields:", ", ".join(f"{k}={sample[k]!r}" for k in name_keys) or "none")
        print("  orderDate present:", "yes" if sample.get("orderDate") else "NO (label will skip the order time)")

    print("\n=== 3. Package count per status ===")
    working = "v2/orders" if res and res[0] == 200 else "orders"
    found_any = False
    for st in ALL_STATUSES:
        r = call(f"{st:<12}", working, {**base_params, "status": st})
        if r and r[0] == 200 and (r[1] or {}).get("totalElements"):
            found_any = True

    print("\n=== 4. Same, wider window (14 days, no status) ===")
    wide = {**base_params, "startDate": int((now - timedelta(days=14)).timestamp() * 1000)}
    call("14 days      ", working, wide)

    print("\n=== Reading the results ===")
    if not found_any:
        print("Auth works but there are NO packages in this window. Likely causes:\n"
              " - no orders were modified in the last days (try --days 14)\n"
              " - the credentials belong to a different seller account / store than the orders\n"
              " - orders are older than the 1-month limit")
    else:
        print("Auth works and packages exist. If 'Created' shows 0 but another status has packages, "
              "your orders are already past 'Created' - run with e.g. --status Picking Invoiced.")
    if res and res[0] == 200 and res_legacy and res_legacy[0] != 200:
        print("v2 works but legacy does not: keep the default. (Legacy is deprecated.)")
    if res and res[0] != 200 and res_legacy and res_legacy[0] == 200:
        print("Legacy works but v2 does not: run the script with --legacy.")

def diagnose(days):
    for n, sl in enumerate(get_sellers(), 1):
        print("\n" + "#" * 70)
        print(f"# SELLER {n}: {seller_tag(sl)}")
        print("#" * 70)
        _diagnose_one(sl, days)


# --------------------------------------------------------------------------- #
# Label drawing
# --------------------------------------------------------------------------- #
def fit_font_size(text, max_width, start, minimum=6):
    size = start
    while size > minimum and pdfmetrics.stringWidth(text, FONT_NAME, size) > max_width:
        size -= 0.5
    return size


def wrap(text, max_width, size, max_lines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(trial, FONT_NAME, size) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def draw_label(c, pkg, W, H, opts):
    m = 4 * mm
    inner_w = W - 2 * m
    # opts.shift_y pushes the whole design down (for printers that start printing early);
    # everything below is laid out from this lower starting line, so nothing gets clipped.
    y = H - m - opts.shift_y * mm

    # --- cargo barcode ------------------------------------------------------
    tracking = str(pkg.get("cargoTrackingNumber") or "")
    compact = H < 120 * mm           # short label such as 100x100: tighter vertical layout
    bar_h = 13 * mm if compact else min(32 * mm, H * 0.2)
    if tracking:
        # scale bar width so the barcode fills the label width
        probe = code128.Code128(tracking, barWidth=1, barHeight=bar_h, quiet=False)
        bw = inner_w / probe.width
        bc = code128.Code128(tracking, barWidth=bw, barHeight=bar_h, quiet=False)
        bc.drawOn(c, m, y - bar_h)
    y -= bar_h + 2 * mm
    c.setFont(FONT_NAME, fit_font_size(tracking, inner_w, 15 if compact else 20))
    c.drawCentredString(W / 2, y - (4.5 if compact else 6) * mm, tracking)
    y -= (6 if compact else 9) * mm

    # --- seller + order time + print time (one small line for tracking) ----
    parts = []
    if getattr(opts, "show_seller", True) and seller_label(pkg):
        parts.append(seller_label(pkg))
    stamp = getattr(opts, "stamp", "both")
    order_ts = fmt_ts(pkg.get("orderDate") or pkg.get("packageLastModifiedDate")) if stamp in ("both", "order") else ""
    if order_ts:
        parts.append("SİP " + order_ts)
    if stamp in ("both", "print"):
        parts.append("BAS " + datetime.now(TR_TZ).strftime("%d.%m.%Y %H:%M"))
    if parts:
        meta = "  |  ".join(parts)
        ms = fit_font_size(meta, inner_w, 9, 5)
        c.setFont(FONT_NAME, ms)
        c.drawCentredString(W / 2, y - ms * 0.8, meta)
        y -= ms * 1.0 + 1.2 * mm

    # --- customer name ------------------------------------------------------
    addr = pkg.get("shipmentAddress") or {}
    name = tr_upper(addr.get("fullName")
                    or f"{pkg.get('customerFirstName', '')} {pkg.get('customerLastName', '')}".strip())
    c.setLineWidth(0.8)
    c.line(m, y, W - m, y)
    y -= 2 * mm
    size = fit_font_size(name, inner_w, 18 if compact else 24, 9)
    c.setFont(FONT_NAME, size)
    c.drawString(m, y - size * 0.8, name)
    y -= size * 1.1 + 1 * mm

    if opts.address:
        text = tr_upper(addr.get("fullAddress") or "")
        c.setFont(FONT_NAME, 8)
        for ln in wrap(text, inner_w, 8, 3):
            y -= 3.4 * mm
            c.drawString(m, y, ln)
        y -= 1 * mm
    c.line(m, y, W - m, y)
    y -= 2 * mm

    # --- product lines ------------------------------------------------------
    footer_h = 5 * mm if opts.footer else 0
    lines = pkg.get("lines") or []
    available = y - (m + footer_h)
    block_h = min(available / max(len(lines), 1), 52 * mm)

    for ln in lines:
        top = y
        qty = int(ln.get("quantity") or 1)
        short, cat_stype = resolve_line_product(ln, pkg, opts)

        qty_txt = f"x{qty}" if qty > 1 else ""
        ptype = cat_stype or pack_type(ln)
        dense = block_h < 23 * mm          # little room (e.g. 2+ products on 100x100): 1 detail line
        qty_size, badge_size = (16, 12) if dense else (26, 20)
        qty_w = pdfmetrics.stringWidth(qty_txt, FONT_NAME, qty_size) + 3 * mm if qty_txt else 0
        badge_w = pdfmetrics.stringWidth(ptype, FONT_NAME, badge_size) + 6 * mm if ptype else 0
        reserved = qty_w + (badge_w + 3 * mm if ptype else 0)
        cap = (24 if compact else 44) if len(lines) == 1 else (20 if compact else 28)
        if dense:
            cap = min(20, block_h * 0.42)
        size = fit_font_size(short, inner_w - reserved, min(cap, block_h / mm * 1.6), 8 if dense else 10)
        baseline = top - size * 0.85
        c.setFont(FONT_NAME, size)
        c.drawString(m, baseline, short)

        right = W - m
        if ptype:                                  # white text on black box
            bh = (6 if dense else 10) * mm
            centre = baseline + size * 0.36
            c.setFillColorRGB(0, 0, 0)
            c.rect(right - badge_w, centre - bh / 2, badge_w, bh, fill=1, stroke=0)
            c.setFillColorRGB(1, 1, 1)
            c.setFont(FONT_NAME, badge_size)
            c.drawCentredString(right - badge_w / 2, centre - badge_size * 0.36, ptype)
            c.setFillColorRGB(0, 0, 0)
            right -= badge_w + 3 * mm
        if qty_txt:
            c.setFont(FONT_NAME, qty_size)
            c.drawRightString(right, baseline, qty_txt)

        if dense:                                  # one compact line instead of the 2x2 grid
            detail = (f"Renk: {ln.get('productColor') or '-'}   Beden: {ln.get('productSize') or '-'}   "
                      f"Stok: {ln.get('stockCode') or '-'}   Barkod: {ln.get('barcode') or '-'}")
            ds = fit_font_size(detail, inner_w, min(10, block_h * 0.22), 5.5)
            c.setFont(FONT_NAME, ds)
            c.drawString(m, top - size * 1.05 - 1 * mm - ds * 0.8, detail)
            y -= block_h
            if len(lines) > 1:
                c.setDash(1, 2)
                c.line(m, y, W - m, y)
                c.setDash()
            continue

        grid_top = top - size * 1.05 - 1.5 * mm
        fields = [
            ("Renk", ln.get("productColor")),
            ("Beden", ln.get("productSize")),
            ("Stok Kodu", ln.get("stockCode")),
            ("Barkod", ln.get("barcode")),
        ]
        lab_off = (2.0 if compact else 2.4) * mm
        row_h = min((8 if compact else 11) * mm if len(lines) == 1 else (6 if compact else 7.5) * mm, (block_h - size * 1.05 - 2 * mm) / 2)
        col_w = inner_w / 2
        for i, (label, value) in enumerate(fields):
            cx = m + (i % 2) * col_w
            cy = grid_top - (i // 2) * row_h
            c.setFont(FONT_NAME, 6.5)
            c.drawString(cx, cy - lab_off, label.upper())
            val = str(value or "-")
            base = (14 if compact else 18) if len(lines) == 1 else (10 if compact else 13)
            base = min(base, max(7, (row_h - lab_off - 1 * mm) / 0.95))   # never taller than the row
            vs = fit_font_size(val, col_w - 2 * mm, base, 6)
            c.setFont(FONT_NAME, vs)
            c.drawString(cx, cy - lab_off - vs * 0.95, val)
        y -= block_h
        if len(lines) > 1:
            c.setDash(1, 2)
            c.line(m, y, W - m, y)
            c.setDash()

    # --- optional footer ----------------------------------------------------
    if opts.footer:
        c.setFont(FONT_NAME, 6.5)
        c.drawString(m, m, f"#{pkg.get('orderNumber', '')}   PKG {pkg.get('shipmentPackageId', '')}")
        c.drawRightString(W - m, m, str(pkg.get("cargoProviderName") or ""))


def build_pdf(packages, out_path, opts):
    W, H = opts.w * mm, opts.h * mm
    c = canvas.Canvas(out_path, pagesize=(W, H))
    c.setTitle("Trendyol labels")
    for pkg in packages:
        draw_label(c, pkg, W, H, opts)
        c.showPage()
    c.save()


def send_to_printer(pdf_path, printer=None):
    """Windows: SumatraPDF (SUMATRA_PATH in .env) at true size. Mac/Linux: lp."""
    import subprocess
    pdf_path = os.path.abspath(pdf_path)
    try:
        if sys.platform.startswith("win"):
            sumatra = os.getenv("SUMATRA_PATH", r"C:\Users\pc\AppData\Local\SumatraPDF\SumatraPDF.exe")
            if not (sumatra and os.path.exists(sumatra)):
                print(f"SUMATRA_PATH ({sumatra}) must point to SumatraPDF.exe (the file, not the folder).")
                return False
            printer_to_use = printer or os.getenv("PRINTER_NAME", "Xprinter XP-470B")
            target = ["-print-to", printer_to_use] if printer_to_use else ["-print-to-default"]
            return subprocess.run([sumatra, *target, "-print-settings", "noscale", "-silent", pdf_path],
                                  timeout=60).returncode == 0
        cmd = ["lp"] + (["-d", printer] if printer else []) + [pdf_path]
        return subprocess.run(cmd, timeout=60).returncode == 0
    except subprocess.TimeoutExpired:
        print("print error: SumatraPDF timed out after 60s.")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"print error: {e}")
        return False


# --------------------------------------------------------------------------- #
# Outsourced products (items you don't stock: label is saved as PDF, not printed)
# --------------------------------------------------------------------------- #
OUTSOURCED_DIR = str(get_data_path("outsourced_labels"))
DEFAULT_OUTSOURCED_FILE = os.getenv("OUTSOURCED_FILE", str(get_data_path("outsourced_products.txt")))


def load_outsourced(path=None):
    """Barcodes from the list file. One per line, '#' starts a comment, '*' works as wildcard
    (e.g. LHLP* ). Re-read on every call, so edits apply without restarting the watcher."""
    path = path or DEFAULT_OUTSOURCED_FILE
    classifier = OutsourcedClassifier(path)
    report = classifier.load(force=True)
    if report.duplicates and VERBOSE:
        print(f"  [Outsourced] Notice: duplicate rules in {path}: {report.duplicates}")
    if report.redundant_rules and VERBOSE:
        print(f"  [Outsourced] Notice: redundant rules in {path}: {report.redundant_rules}")
    return classifier.patterns


def classify(pkg, patterns):
    """'normal' (nothing outsourced) | 'outsourced' (every product) | 'mixed' (some products)."""
    lines = pkg.get("lines") or []
    if not patterns or not lines:
        return "normal"
    hits = []
    for ln in lines:
        bc = (ln.get("barcode") or "").strip().upper()
        norm_bc = bc.replace("i", "İ").replace("ı", "I")
        hits.append(bool(norm_bc) and any(fnmatch.fnmatchcase(norm_bc, pat.upper()) for pat in patterns))
    if all(hits):
        return "outsourced"
    return "mixed" if any(hits) else "normal"


def route(pkg, patterns, mixed="both"):
    """-> (kind, print_it, save_pdf_it). Mixed packages follow --mixed (both|print|save)."""
    kind = classify(pkg, patterns)
    if kind == "outsourced":
        return kind, False, True
    if kind == "mixed":
        return kind, mixed in ("both", "print"), mixed in ("both", "save")
    return kind, True, False


def safe_part(text, limit=40):
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text or "")
    t = re.sub(r"\s+", "_", t.strip())
    return t.strip("._")[:limit]


def save_outsourced_pdf(pkg, label_opts, kind="outsourced"):
    """Save ONE package's label as  outsourced_labels/<date>/<date>_<Customer>_<PRODUCT>.pdf"""
    day = datetime.now(TR_TZ).strftime("%Y-%m-%d")
    folder = os.path.join(OUTSOURCED_DIR, day)
    os.makedirs(folder, exist_ok=True)

    cust = safe_part((pkg.get("shipmentAddress") or {}).get("fullName")) or "musteri"
    names = []
    for ln in pkg.get("lines") or []:
        short_name, _ = resolve_line_product(ln, pkg, label_opts)
        n = safe_part(short_name, 25)
        if n and n not in names:
            names.append(n)
    prod = "+".join(names[:3]) or "urun"
    base = f"{day}_{cust}_{prod}" + ("_MIXED" if kind == "mixed" else "")

    path = os.path.join(folder, base + ".pdf")
    n = 2
    while os.path.exists(path):                      # same customer + product on the same day
        path = os.path.join(folder, f"{base}_{n}.pdf")
        n += 1
    build_pdf([pkg], path, label_opts)
    return path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", nargs="+", default=["Picking"],
                    help="package statuses to fetch (default: Picking = panel's 'İşleme Alınanlar')")
    ap.add_argument("--days", type=int, default=7, help="look back N days (default 7)")
    ap.add_argument("--order", help="only this orderNumber")
    ap.add_argument("--input", help="read packages from a saved JSON file instead of the API")
    ap.add_argument("--save-json", help="also dump fetched packages to this file")
    ap.add_argument("--out", default="labels.pdf")
    ap.add_argument("--size", default=os.getenv("LABEL_SIZE", "100x100"),
                    help="label size in mm, WxH (default: LABEL_SIZE from .env, else 100x100)")
    ap.add_argument("--sort", choices=["none", "product", "name"], default="none",
                    help="product = group identical products together for faster packing")
    ap.add_argument("--name-words", type=int, default=1, help="words of productName to print (default 1)")
    ap.add_argument("--overrides", help="JSON file {barcode_or_stockCode: 'Short Name'}")
    ap.add_argument("--catalog", default=os.getenv("PRODUCTS_FILE", str(get_data_path("products.json"))),
                    help="path to products.json catalog")
    ap.add_argument("--no-catalog", action="store_true",
                    help="disable catalog lookup and use legacy first-word extraction")
    ap.add_argument("--unknown-file", default=os.getenv("UNKNOWN_PRODUCTS_FILE", str(get_data_path("unknown_products.json"))),
                    help="path to unknown_products.json")
    ap.add_argument("--preview", action="store_true",
                    help="generate PDF but explicitly guarantee no print job is dispatched")
    ap.add_argument("--shift-y", type=float,
                    default=float(os.getenv("LABEL_SHIFT_Y_MM", "29")),
                    help="move the whole label content DOWN by this many mm (default 29, or "
                         "LABEL_SHIFT_Y_MM from .env). Raise it if the barcode still spills onto "
                         "the previous label, lower it if the bottom gets cut.")
    ap.add_argument("--outsourced-file", default=DEFAULT_OUTSOURCED_FILE,
                    help="list of barcodes you don't stock (default outsourced_products.txt): those labels "
                         "are saved as PDF in outsourced_labels/<date>/ instead of being printed")
    ap.add_argument("--include-outsourced", action="store_true", help="ignore the outsourced list, print everything")
    ap.add_argument("--mixed", choices=["both", "print", "save"], default="both",
                    help="orders with outsourced AND in-stock products: print+save a copy (default), "
                         "only print, or only save")
    ap.add_argument("--seller", help="only this seller (id or part of its name)")
    ap.add_argument("--stamp", choices=["both", "order", "print", "none"], default="both",
                    help="date/time on the label: order time (SİP), print time (BAS), both (default) or none")
    ap.add_argument("--no-seller", dest="show_seller", action="store_false", help="don't print the seller name/id")
    ap.add_argument("--address", action="store_true", help="print the delivery address too")
    ap.add_argument("--footer", action="store_true", help="print order no. / package id / courier")
    ap.add_argument("--font", help="path to a bold TTF with Turkish glyphs")
    ap.add_argument("--print", dest="printer", nargs="?", const="__env__",
                    help="print the PDF now. Optional printer name; without it PRINTER_NAME from .env is used")
    ap.add_argument("--diagnose", action="store_true", help="test credentials/endpoint/statuses and exit")
    ap.add_argument("--verbose", action="store_true", help="print every API request and result count")
    ap.add_argument("--legacy", action="store_true", help="use deprecated /orders instead of /v2/orders")
    opts = ap.parse_args()

    global VERBOSE, USE_LEGACY
    VERBOSE, USE_LEGACY = opts.verbose, opts.legacy
    if opts.seller:
        select_sellers(opts.seller)
    if opts.diagnose:
        diagnose(opts.days)
        return

    opts.w, opts.h = (float(x) for x in opts.size.lower().split("x"))
    opts.overrides = json.load(open(opts.overrides, encoding="utf-8")) if opts.overrides else {}
    register_font(opts.font)

    if opts.input:
        data = json.load(open(opts.input, encoding="utf-8"))
        packages = data["content"] if isinstance(data, dict) else data
    else:
        packages = fetch_packages(opts.status, opts.days, opts.order)

    if opts.save_json:
        json.dump(packages, open(opts.save_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if not packages:
        sys.exit("No packages found. Run again with --diagnose to see why "
                 "(wrong status? credentials? empty window?).")

    def first_line_key(p):
        ln = (p.get("lines") or [{}])[0]
        s_name, _ = resolve_line_product(ln, p, opts)
        return (s_name, ln.get("productColor") or "", ln.get("productSize") or "")

    if opts.sort == "product":
        packages.sort(key=first_line_key)
    elif opts.sort == "name":
        packages.sort(key=lambda p: (p.get("shipmentAddress") or {}).get("fullName", ""))

    patterns = [] if opts.include_outsourced else load_outsourced(opts.outsourced_file)
    if patterns:
        keep, saved, mixed_n = [], 0, 0
        for p in packages:
            kind, do_print, do_save = route(p, patterns, opts.mixed)
            if do_save:
                path = save_outsourced_pdf(p, opts, kind)
                saved += 1
                mixed_n += kind == "mixed"
                print(f"  {'MIXED' if kind == 'mixed' else 'outsourced'} -> {path}")
            if do_print:
                keep.append(p)
        packages = keep
        print(f"Outsourced list: {len(patterns)} barcode rule(s). Saved {saved} PDF(s) in {OUTSOURCED_DIR}/"
              + (f" ({mixed_n} mixed order(s): check these by hand)" if mixed_n else ""))
        if not packages:
            sys.exit("Nothing left to print: every package was outsourced.")

    counts = {"ÇİFT": 0, "TEK": 0, None: 0}
    for p in packages:
        for ln in p.get("lines") or []:
            _, cat_stype = resolve_line_product(ln, p, opts)
            t = cat_stype or pack_type(ln)
            counts[t if t in counts else None] += 1
            if t is None and opts.verbose:
                print(f"  no Çift/Tek detected in: {ln.get('productName')}")
    print(f"Çift: {counts['ÇİFT']}  Tek: {counts['TEK']}  not detected: {counts[None]}"
          + ("" if not counts[None] else "  (run with --verbose to list them)"))

    build_pdf(packages, opts.out, opts)
    print(f"{len(packages)} labels -> {opts.out}")

    if opts.printer and not opts.preview:
        printer = os.getenv("PRINTER_NAME", "Xprinter XP-470B") if opts.printer == "__env__" else opts.printer
        ok = send_to_printer(opts.out, printer)
        print("sent to printer" if ok else "PRINT FAILED (see message above)")
    elif opts.preview:
        print(f"[PREVIEW MODE] Physical printing skipped. Generated label PDF at: {opts.out}")


if __name__ == "__main__":
    main()
