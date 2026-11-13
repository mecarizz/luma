"""Data models for isolated multi-seller profiles and cargo configurations."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.security import decrypt_secret, encrypt_secret

CARGO_PROVIDERS: Dict[str, str] = {
    "DHLECOMMP": "DHL eCommerce Marketplace",
    "TEX": "Trendyol Express (TEX)",
    "YK": "Yurtiçi Kargo",
    "ARAS": "Aras Kargo",
    "MNG": "MNG Kargo",
    "PTT": "PTT Kargo",
    "SURAT": "Sürat Kargo",
    "SENDEO": "Sendeo",
    "HOROZ": "Horoz Lojistik",
    "CEVA": "Ceva Lojistik",
}

DEFAULT_STATUSES = ["Created", "Picking"]


@dataclass
class SellerProfile:
    # 1. General & Identity
    seller_id: str
    name: str = ""
    is_active: bool = True
    monitoring_enabled: bool = True

    # 2. Trendyol API Credentials (stored encrypted at rest)
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://apigw.trendyol.com/integration"

    # 3. Operational Polling
    polling_interval_seconds: int = 30
    lookback_hours: float = 48.0
    statuses: List[str] = field(default_factory=lambda: list(DEFAULT_STATUSES))

    # 4. Cargo Settings
    preferred_cargo: str = "DHLECOMMP"
    cargo_switch_enabled: bool = True
    fallback_behavior: str = "fail_and_hold"  # "fail_and_hold" | "print_original"
    print_on_fail: bool = False
    no_switch_outsourced: bool = True
    mixed_order_behavior: str = "both"  # "both" | "print" | "save"

    # 5. Label & Physical Thermal Layout (Default: 100x100mm, 29mm shift)
    label_size: str = "100x100"
    label_shift_y_mm: float = 29.0
    show_seller_name: bool = True
    print_timestamp: str = "both"  # "both" | "order" | "print" | "none"
    include_address: bool = False
    include_footer: bool = False

    # 6. Printing
    printer_name: str = ""
    sumatra_path: str = str(
        Path.home() / "AppData" / "Local" / "SumatraPDF" / "SumatraPDF.exe"
    )
    auto_print: bool = True

    # 7. Catalog & Outsourced Isolation
    catalog_mode: str = "shared"  # "shared" | "isolated"
    outsourced_mode: str = "isolated"  # "isolated" | "shared"
    outsourced_rules: List[str] = field(default_factory=list)

    # 8. Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def display_tag(self) -> str:
        return self.name if self.name else f"Seller {self.seller_id}"

    @property
    def raw_api_key(self) -> str:
        return decrypt_secret(self.api_key)

    @property
    def raw_api_secret(self) -> str:
        return decrypt_secret(self.api_secret)

    @property
    def credential_error(self) -> Optional[str]:
        for label, stored, raw in (
            ("API key", self.api_key, self.raw_api_key),
            ("API secret", self.api_secret, self.raw_api_secret),
        ):
            if not raw:
                return f"{label} is missing."
            if stored.startswith("dpapi:") and raw.startswith("dpapi:"):
                return (
                    f"{label} could not be decrypted for the current Windows user. "
                    "Re-enter it in Seller Config while signed in as the account that runs Luma."
                )
        return None

    def to_dict(self, encrypt_credentials: bool = True) -> Dict[str, Any]:
        data = asdict(self)
        if encrypt_credentials:
            data["api_key"] = encrypt_secret(self.raw_api_key)
            data["api_secret"] = encrypt_secret(self.raw_api_secret)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SellerProfile:
        clean_data = dict(data)
        sid = str(clean_data.get("seller_id", "")).strip().strip("'\"")
        clean_data["seller_id"] = sid
        clean_data["name"] = str(clean_data.get("name", "")).strip()
        # Ensure list of statuses
        if isinstance(clean_data.get("statuses"), str):
            clean_data["statuses"] = [s.strip() for s in clean_data["statuses"].split(",") if s.strip()]

        # Filter known fields
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in clean_data.items() if k in valid_fields}
        return cls(**filtered)
