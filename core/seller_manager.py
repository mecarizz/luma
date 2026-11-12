"""Load, validate, and persist isolated seller profiles."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional

from core.config import load_sellers_from_env
from core.paths import get_data_path
from core.security import encrypt_secret
from core.seller_models import SellerProfile


class SellerManager:
    """Manage seller profiles with one-time migration from configured environment values."""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = str(file_path or get_data_path(os.path.join("data", "sellers.json")))
        self._profiles: Dict[str, SellerProfile] = {}
        self.load(force=True)

    def load(self, force: bool = False) -> None:
        if os.path.exists(self.file_path) and os.path.getsize(self.file_path) > 0:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                profiles: Dict[str, SellerProfile] = {}
                raw_list = data.get("sellers", []) if isinstance(data, dict) else data
                if not isinstance(raw_list, list):
                    raise ValueError("the 'sellers' value must be a list")
                for item in raw_list:
                    if isinstance(item, dict) and item.get("seller_id"):
                        prof = SellerProfile.from_dict(item)
                        profiles[prof.seller_id] = prof
                self._profiles = profiles
                return
            except Exception as e:
                raise ValueError(f"Could not load seller profiles from '{self.file_path}': {e}") from e

        # Migrate configured environment sellers once; never create fake profiles.
        self._migrate_from_env()

    def _migrate_from_env(self) -> None:
        profiles: Dict[str, SellerProfile] = {}
        for seller in load_sellers_from_env():
            profile = SellerProfile(
                seller_id=seller.id,
                name=seller.name or f"Seller {seller.id}",
                api_key=encrypt_secret(seller.key),
                api_secret=encrypt_secret(seller.secret),
                preferred_cargo="DHLECOMMP",
            )
            profiles[profile.seller_id] = profile

        self._profiles = profiles
        if profiles:
            self.save()

    def save(self) -> None:
        parent = os.path.dirname(self.file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if os.path.exists(self.file_path) and os.path.getsize(self.file_path) > 0:
            backup_dir = os.path.join(parent or ".", "backups")
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            shutil.copy2(self.file_path, os.path.join(backup_dir, f"sellers_{ts}.json"))

        payload = {
            "_version": "1.0",
            "_updated_at": datetime.now().isoformat(timespec="seconds"),
            "sellers": [p.to_dict(encrypt_credentials=True) for p in self._profiles.values()],
        }

        tmp_path = self.file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.file_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

    def list_all(self) -> List[SellerProfile]:
        return sorted(self._profiles.values(), key=lambda p: p.seller_id)

    def get(self, seller_id: str) -> Optional[SellerProfile]:
        sid = str(seller_id).strip()
        return self._profiles.get(sid)

    def save_profile(self, profile: SellerProfile) -> List[str]:
        """Validate and commit a seller profile."""
        errors = self.validate_profile(profile)
        if errors:
            return errors

        profile.seller_id = str(profile.seller_id).strip()
        profile.updated_at = datetime.now().isoformat(timespec="seconds")
        previous = self._profiles.get(profile.seller_id)
        self._profiles[profile.seller_id] = profile
        try:
            self.save()
        except Exception:
            if previous is None:
                self._profiles.pop(profile.seller_id, None)
            else:
                self._profiles[profile.seller_id] = previous
            raise
        return []

    def delete_profile(self, seller_id: str) -> bool:
        sid = str(seller_id).strip()
        if sid in self._profiles:
            profile = self._profiles.pop(sid)
            try:
                self.save()
            except Exception:
                self._profiles[sid] = profile
                raise
            return True
        return False

    def toggle_monitoring(self, seller_id: str, enabled: bool) -> bool:
        prof = self.get(seller_id)
        if prof:
            prof.monitoring_enabled = enabled
            self.save_profile(prof)
            return True
        return False

    def validate_profile(self, profile: SellerProfile) -> List[str]:
        errors: List[str] = []
        sid = str(profile.seller_id or "").strip()
        if not sid:
            errors.append("Seller ID is required.")
        elif not sid.isdigit():
            errors.append(f"Seller ID '{sid}' must contain digits only.")

        if not profile.raw_api_key:
            errors.append("Trendyol API Key is required.")
        if not profile.raw_api_secret:
            errors.append("Trendyol API Secret is required.")

        if profile.label_shift_y_mm < 0:
            errors.append("Vertical shift (mm) cannot be negative.")

        return errors
