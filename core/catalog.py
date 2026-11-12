"""Permanent barcode product catalog and multi-stage identification engine.

Provides high-performance, in-memory cached lookup, deterministic priority resolution,
Turkish-aware barcode normalization, wildcard pattern support, safe atomic updates,
and automated backups.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TR_TZ = timezone(timedelta(hours=3))  # Turkey: UTC+3 all year


def normalize_identifier(identifier: Optional[str]) -> str:
    """Normalize a barcode or stock code consistently.

    Preserves hyphens, dots, underscores, and alphanumeric characters.
    Handles Turkish-specific uppercase mapping: i -> İ, ı -> I.
    """
    if identifier is None:
        return ""
    s = str(identifier).strip()
    # Remove invisible zero-width or formatting characters
    s = s.replace("\u200b", "").replace("\ufeff", "")
    return s.replace("i", "İ").replace("ı", "I").upper()


@dataclass
class ProductItem:
    barcode: str
    display_name: str
    stock_code: Optional[str] = None
    seller: Optional[str] = None
    category: Optional[str] = None
    product_type: Optional[str] = None
    size_type: Optional[str] = None  # "ÇİFT", "TEK", or None
    color: Optional[str] = None
    size: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, barcode: str, data: Dict[str, Any]) -> ProductItem:
        b_norm = normalize_identifier(barcode or data.get("barcode"))
        name = (data.get("display_name") or data.get("name") or "").strip()
        stock = normalize_identifier(data.get("stock_code") or data.get("stockCode"))
        seller = data.get("seller") or data.get("seller_name")
        category = data.get("category")
        ptype = data.get("product_type") or data.get("productType")
        stype = data.get("size_type") or data.get("sizeType")
        if stype:
            stype = str(stype).upper().strip()
            if stype not in ("ÇİFT", "TEK"):
                stype = None
        color = data.get("color") or data.get("productColor")
        size = data.get("size") or data.get("productSize")
        notes = data.get("notes")
        created_at = data.get("created_at")
        updated_at = data.get("updated_at")

        known_keys = {
            "barcode", "display_name", "name", "stock_code", "stockCode",
            "seller", "seller_name", "category", "product_type", "productType",
            "size_type", "sizeType", "color", "productColor", "size", "productSize",
            "notes", "created_at", "updated_at"
        }
        extras = {k: v for k, v in data.items() if k not in known_keys}

        return cls(
            barcode=b_norm,
            display_name=name,
            stock_code=stock if stock else None,
            seller=seller,
            category=category,
            product_type=ptype,
            size_type=stype,
            color=color,
            size=size,
            notes=notes,
            created_at=created_at,
            updated_at=updated_at,
            extra_fields=extras,
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "barcode": self.barcode,
            "display_name": self.display_name,
            "stock_code": self.stock_code,
            "seller": self.seller,
            "category": self.category,
            "product_type": self.product_type,
            "size_type": self.size_type,
            "color": self.color,
            "size": self.size,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.extra_fields:
            d.update(self.extra_fields)
        return d


@dataclass
class WildcardRule:
    pattern: str
    display_name: str
    seller: Optional[str] = None
    category: Optional[str] = None
    size_type: Optional[str] = None

    def matches(self, barcode: str) -> bool:
        norm_b = normalize_identifier(barcode)
        norm_pat = normalize_identifier(self.pattern)
        return fnmatch.fnmatchcase(norm_b, norm_pat)


class ProductCatalog:
    """Thread-safe, cached product database manager."""

    def __init__(self, catalog_path: str = "products.json"):
        self.catalog_path = catalog_path
        self._products: Dict[str, ProductItem] = {}  # barcode -> ProductItem
        self._stock_index: Dict[str, List[ProductItem]] = {}  # stock_code -> list
        self._wildcards: List[WildcardRule] = []
        self._last_mtime: float = -1.0
        self.load(force=True)

    def load(self, force: bool = False) -> None:
        """Load catalog from disk if file mtime changed or force=True."""
        if not os.path.exists(self.catalog_path) or os.path.getsize(self.catalog_path) == 0:
            self._products = {}
            self._stock_index = {}
            self._wildcards = []
            self._last_mtime = -1.0
            return

        try:
            mtime = os.path.getmtime(self.catalog_path)
            if not force and mtime == self._last_mtime:
                return

            with open(self.catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            products: Dict[str, ProductItem] = {}
            stock_idx: Dict[str, List[ProductItem]] = {}
            wildcards: List[WildcardRule] = []

            # Format A: {"_version": "1.0", "products": {...}, "wildcards": [...]}
            if isinstance(data, dict) and "products" in data and isinstance(data["products"], dict):
                raw_prods = data["products"]
                for pat_item in data.get("wildcards", []):
                    if isinstance(pat_item, dict) and pat_item.get("pattern"):
                        wildcards.append(WildcardRule(
                            pattern=pat_item["pattern"],
                            display_name=pat_item.get("display_name") or pat_item.get("name") or "",
                            seller=pat_item.get("seller"),
                            category=pat_item.get("category"),
                            size_type=pat_item.get("size_type"),
                        ))
            # Format B: Flat dictionary {"LHLPK": {...}, ...}
            elif isinstance(data, dict):
                raw_prods = data
            else:
                raw_prods = {}

            for raw_key, raw_val in raw_prods.items():
                if isinstance(raw_val, dict):
                    prod = ProductItem.from_dict(raw_key, raw_val)
                    if prod.barcode:
                        products[prod.barcode] = prod
                        if prod.stock_code:
                            stock_idx.setdefault(prod.stock_code, []).append(prod)

            # Sort wildcards by pattern length descending (longest pattern first)
            wildcards.sort(key=lambda r: len(r.pattern), reverse=True)

            self._products = products
            self._stock_index = stock_idx
            self._wildcards = wildcards
            self._last_mtime = mtime

        except Exception as e:
            # Avoid crashing if JSON is temporarily invalid during external edits
            print(f"[ProductCatalog] Warning: Failed to load '{self.catalog_path}': {e}")

    def save(self) -> None:
        """Atomically persist catalog to disk with automated timestamped backup."""
        # Ensure parent directory exists
        parent = os.path.dirname(self.catalog_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Automatic backup if original exists and has content
        if os.path.exists(self.catalog_path) and os.path.getsize(self.catalog_path) > 0:
            backup_dir = os.path.join(parent or ".", "backups")
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"products_{ts}.json")
            try:
                shutil.copy2(self.catalog_path, backup_path)
            except OSError:
                pass

        payload = {
            "_version": "1.0",
            "_updated_at": datetime.now().isoformat(timespec="seconds"),
            "products": {b: p.to_dict() for b, p in self._products.items()},
            "wildcards": [
                {
                    "pattern": w.pattern,
                    "display_name": w.display_name,
                    "seller": w.seller,
                    "category": w.category,
                    "size_type": w.size_type,
                }
                for w in self._wildcards
            ],
        }

        tmp_path = self.catalog_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        os.replace(tmp_path, self.catalog_path)
        self._last_mtime = os.path.getmtime(self.catalog_path)

    # ----------------------------------------------------------------------- #
    # Query Operations
    # ----------------------------------------------------------------------- #
    def get_by_barcode(self, barcode: Optional[str]) -> Optional[ProductItem]:
        self.load()  # check hot-reload
        norm = normalize_identifier(barcode)
        return self._products.get(norm)

    def get_by_stock_code(self, stock_code: Optional[str], seller: Optional[str] = None) -> Optional[ProductItem]:
        self.load()
        norm = normalize_identifier(stock_code)
        candidates = self._stock_index.get(norm, [])
        if not candidates:
            return None
        if seller:
            norm_seller = seller.strip().lower()
            matching = [p for p in candidates if (p.seller or "").strip().lower() == norm_seller]
            if len(matching) == 1:
                return matching[0]
        # If single candidate globally, return it
        if len(candidates) == 1:
            return candidates[0]
        return None

    def match_wildcard(self, barcode: Optional[str]) -> Optional[WildcardRule]:
        self.load()
        norm = normalize_identifier(barcode)
        if not norm:
            return None
        for rule in self._wildcards:
            if rule.matches(norm):
                return rule
        return None

    def resolve(
        self,
        barcode: Optional[str],
        stock_code: Optional[str] = None,
        product_name: Optional[str] = None,
        overrides: Optional[Dict[str, str]] = None,
        seller: Optional[str] = None,
        name_words: int = 1,
    ) -> Tuple[str, Optional[str], str]:
        """Multi-stage deterministic product resolver.

        Returns: (resolved_display_name, size_type, resolution_source)
        Sources:
          - "catalog_barcode" (Exact barcode catalog match)
          - "catalog_stock_code" (Exact stock code catalog match)
          - "catalog_wildcard" (Wildcard pattern match)
          - "manual_override" (Legacy overrides dictionary)
          - "trendyol_fallback" (Extracted from Trendyol productName)
        """
        self.load()

        # 1. Exact Barcode Match
        prod = self.get_by_barcode(barcode)
        if prod and prod.display_name:
            return prod.display_name.upper(), prod.size_type, "catalog_barcode"

        # 2. Exact Stock Code Match
        prod_stock = self.get_by_stock_code(stock_code, seller=seller)
        if prod_stock and prod_stock.display_name:
            return prod_stock.display_name.upper(), prod_stock.size_type, "catalog_stock_code"

        # 3. Wildcard Pattern Match
        w_rule = self.match_wildcard(barcode)
        if w_rule and w_rule.display_name:
            return w_rule.display_name.upper(), w_rule.size_type, "catalog_wildcard"

        # 4. Legacy Overrides Fallback
        if overrides:
            for key in (normalize_identifier(barcode), normalize_identifier(stock_code)):
                if key and key in overrides:
                    return str(overrides[key]).upper(), None, "manual_override"
            # Also check raw non-normalized keys for backward compatibility
            for key in (barcode, stock_code):
                if key and key in overrides:
                    return str(overrides[key]).upper(), None, "manual_override"

        # 5. Trendyol Fallback
        raw_name = (product_name or "").strip()
        if raw_name:
            words = raw_name.split()[:name_words]
            fallback_name = " ".join(words).upper() or "?"
        else:
            fallback_name = "?"

        return fallback_name, None, "trendyol_fallback"

    # ----------------------------------------------------------------------- #
    # Mutation Operations
    # ----------------------------------------------------------------------- #
    def add_or_update(self, item: ProductItem) -> None:
        self.load()
        now_iso = datetime.now().isoformat(timespec="seconds")
        if item.barcode in self._products:
            orig = self._products[item.barcode]
            item.created_at = orig.created_at or now_iso
            item.updated_at = now_iso
        else:
            item.created_at = now_iso
            item.updated_at = now_iso

        self._products[item.barcode] = item
        # Rebuild stock index
        self._stock_index = {}
        for p in self._products.values():
            if p.stock_code:
                self._stock_index.setdefault(p.stock_code, []).append(p)
        self.save()

    def delete(self, barcode: str) -> bool:
        self.load()
        norm = normalize_identifier(barcode)
        if norm in self._products:
            del self._products[norm]
            self._stock_index = {}
            for p in self._products.values():
                if p.stock_code:
                    self._stock_index.setdefault(p.stock_code, []).append(p)
            self.save()
            return True
        return False

    def list_all(self) -> List[ProductItem]:
        self.load()
        return sorted(self._products.values(), key=lambda p: p.barcode)
