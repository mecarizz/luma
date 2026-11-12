"""Centralized configuration loader and validator.

Establishes a single source of truth for all seller credentials, physical printer
settings, application directories, and operational parameters.
"""
from __future__ import annotations

import base64
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.paths import get_data_path

try:
    from dotenv import load_dotenv
    # Load .env from current directory or parent directory if present
    load_dotenv()
except ImportError:
    pass


# --------------------------------------------------------------------------- #
# Hardware Defaults (Tested & verified for direct thermal printing setup)
# --------------------------------------------------------------------------- #
DEFAULT_LABEL_SIZE = "100x100"
DEFAULT_LABEL_SHIFT_Y_MM = 29.0
DEFAULT_PRINTER_NAME = "Xprinter XP-470B"
DEFAULT_SUMATRA_PATH = r"C:\Users\pc\AppData\Local\SumatraPDF\SumatraPDF.exe"
DEFAULT_BASE_URL = "https://apigw.trendyol.com/integration"
DEFAULT_DHL_CODE = "DHLECOMMP"


@dataclass
class SellerConfig:
    id: str
    key: str
    secret: str
    name: str = ""

    @property
    def display_tag(self) -> str:
        return self.name if self.name else self.id

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "key": self.key,
            "secret": self.secret,
            "name": self.name,
        }


@dataclass
class AppConfig:
    # Hardware & Thermal Printer Settings
    label_size: str = DEFAULT_LABEL_SIZE
    label_width_mm: float = 100.0
    label_height_mm: float = 100.0
    label_shift_y_mm: float = DEFAULT_LABEL_SHIFT_Y_MM
    printer_name: str = DEFAULT_PRINTER_NAME
    sumatra_path: str = DEFAULT_SUMATRA_PATH

    # API & Integration Settings
    base_url: str = DEFAULT_BASE_URL
    dhl_code: str = DEFAULT_DHL_CODE
    sellers: List[SellerConfig] = field(default_factory=list)

    # Operational Settings
    poll_interval: int = 30
    lookback_hours: float = 48.0
    max_switch_attempts: int = 3
    retry_after_seconds: int = 300

    # File Paths
    products_file: str = "products.json"
    unknown_products_file: str = "unknown_products.json"
    outsourced_file: str = "outsourced_products.txt"
    state_file: str = "printed_packages.json"
    log_file: str = "watcher.log"
    labels_out_dir: str = "labels_out"
    outsourced_dir: str = "outsourced_labels"


def mask_secret(val: Optional[str]) -> str:
    """Mask sensitive API keys/secrets for logs and diagnostics."""
    if not val:
        return "(none)"
    val = str(val).strip()
    if len(val) <= 6:
        return "***"
    return f"{val[:3]}...{val[-3:]} (len {len(val)})"


def parse_label_size(size_str: str) -> Tuple[float, float]:
    """Parse '100x100' or '100x150' into (width_mm, height_mm)."""
    clean = (size_str or DEFAULT_LABEL_SIZE).lower().strip()
    parts = clean.split("x")
    if len(parts) != 2:
        raise ValueError(f"Invalid LABEL_SIZE format '{size_str}'. Expected 'WIDTHxHEIGHT', e.g. '100x100'.")
    try:
        w, h = float(parts[0]), float(parts[1])
        if w <= 0 or h <= 0:
            raise ValueError
        return w, h
    except ValueError:
        raise ValueError(f"Invalid dimensions in LABEL_SIZE '{size_str}'. Values must be positive numbers.")


def resolve_file_path(primary: str, fallback_candidates: Optional[List[str]] = None) -> str:
    """Return an existing path if one of the candidates exists, else primary."""
    candidates = [primary] + (fallback_candidates or [])
    for cand in candidates:
        if cand and os.path.exists(cand):
            return cand
    return primary


def load_sellers_from_env() -> List[SellerConfig]:
    """Parse all configured Trendyol sellers from environment variables."""
    names_map: Dict[str, str] = {}
    seller_names_env = os.getenv("SELLER_NAMES") or ""
    for part in seller_names_env.replace(";", ",").split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            names_map[k.strip()] = v.strip()

    sellers: List[SellerConfig] = []
    # Check numbered sellers (1..20)
    for i in range(1, 21):
        sid = os.getenv(f"TRENDYOL_SELLER_ID_{i}")
        key = os.getenv(f"TRENDYOL_API_KEY_{i}")
        secret = os.getenv(f"TRENDYOL_API_SECRET_{i}")
        if not (sid or key or secret):
            continue
        if not (sid and key and secret):
            raise ValueError(
                f"Seller {i} configuration incomplete: TRENDYOL_SELLER_ID_{i}, "
                f"TRENDYOL_API_KEY_{i}, and TRENDYOL_API_SECRET_{i} are all required."
            )
        sid_clean = sid.strip().strip("'\"")
        name = (os.getenv(f"TRENDYOL_SELLER_NAME_{i}") or names_map.get(sid_clean) or "").strip().strip("'\"")
        sellers.append(
            SellerConfig(
                id=sid_clean,
                key=key.strip().strip("'\""),
                secret=secret.strip().strip("'\""),
                name=name,
            )
        )

    # Legacy unnumbered fallback
    if not sellers:
        sid = os.getenv("TRENDYOL_SELLER_ID")
        key = os.getenv("TRENDYOL_API_KEY")
        secret = os.getenv("TRENDYOL_API_SECRET")
        if sid and key and secret:
            sid_clean = sid.strip().strip("'\"")
            name = (os.getenv("TRENDYOL_SELLER_NAME") or names_map.get(sid_clean) or "").strip().strip("'\"")
            sellers.append(
                SellerConfig(
                    id=sid_clean,
                    key=key.strip().strip("'\""),
                    secret=secret.strip().strip("'\""),
                    name=name,
                )
            )

    # Validate duplicate seller IDs
    ids = [s.id for s in sellers]
    if len(set(ids)) != len(ids):
        duplicates = [x for x in ids if ids.count(x) > 1]
        raise ValueError(f"Duplicate seller ID detected in configuration: {duplicates}")

    return sellers


def get_config() -> AppConfig:
    """Load, validate, and return the centralized AppConfig instance."""
    # Label Size & Shift
    raw_size = os.getenv("LABEL_SIZE", DEFAULT_LABEL_SIZE)
    w, h = parse_label_size(raw_size)

    raw_shift = os.getenv("LABEL_SHIFT_Y_MM")
    try:
        shift_y = float(raw_shift) if raw_shift is not None else DEFAULT_LABEL_SHIFT_Y_MM
    except (ValueError, TypeError):
        raise ValueError(f"Invalid LABEL_SHIFT_Y_MM '{raw_shift}'. Must be a valid number (e.g. 29).")

    # Printer & Sumatra
    printer_name = os.getenv("PRINTER_NAME", DEFAULT_PRINTER_NAME)
    sumatra_path = os.getenv("SUMATRA_PATH", DEFAULT_SUMATRA_PATH)

    # File paths (search current directory first, then data/ subdirectory)
    products_file = resolve_file_path(
        os.getenv("PRODUCTS_FILE", str(get_data_path("products.json"))),
        ["data/products.json"]
    )
    unknown_products_file = resolve_file_path(
        os.getenv("UNKNOWN_PRODUCTS_FILE", str(get_data_path("unknown_products.json"))),
        ["data/unknown_products.json"]
    )
    outsourced_file = resolve_file_path(
        os.getenv("OUTSOURCED_FILE", str(get_data_path("outsourced_products.txt"))),
        ["data/outsourced_products.txt"]
    )
    state_file = resolve_file_path(
        os.getenv("STATE_FILE", str(get_data_path("printed_packages.json"))),
        ["data/printed_packages.json"]
    )

    sellers = load_sellers_from_env()

    return AppConfig(
        label_size=raw_size,
        label_width_mm=w,
        label_height_mm=h,
        label_shift_y_mm=shift_y,
        printer_name=printer_name,
        sumatra_path=sumatra_path,
        base_url=os.getenv("TRENDYOL_BASE_URL", DEFAULT_BASE_URL),
        dhl_code=os.getenv("DHL_CARRIER_CODE", DEFAULT_DHL_CODE),
        sellers=sellers,
        poll_interval=int(os.getenv("POLL_INTERVAL", "30")),
        lookback_hours=float(os.getenv("LOOKBACK_HOURS", "48.0")),
        products_file=products_file,
        unknown_products_file=unknown_products_file,
        outsourced_file=outsourced_file,
        state_file=state_file,
        log_file=os.getenv("LOG_FILE", "watcher.log"),
    )


def build_api_headers(seller: SellerConfig | Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Build standard Trendyol Basic Auth and SelfIntegration User-Agent headers."""
    if isinstance(seller, SellerConfig):
        sid, key, secret = seller.id, seller.key, seller.secret
    else:
        sid = seller.get("id", "")
        key = seller.get("key", "")
        secret = seller.get("secret", "")

    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "User-Agent": f"{sid} - SelfIntegration",
        "Accept": "application/json",
    }
    return sid, headers
