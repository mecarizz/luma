"""Qt worker that runs the proven Trendyol watcher for saved seller profiles."""
from __future__ import annotations

import logging
import sys
import threading
import time
from types import SimpleNamespace
from typing import Iterable, List

from PySide6.QtCore import QThread, Signal

from core.logger import setup_logger
from core.paths import get_data_path
from core.seller_models import SellerProfile


class _QtLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        self.signal.emit(self.format(record))


class SellerWorker(QThread):
    log_emitted = Signal(str)
    order_processed = Signal(str, str, str, str, str)
    status_updated = Signal(str, str)

    def __init__(self, profiles: Iterable[SellerProfile]):
        super().__init__()
        self._profiles: List[SellerProfile] = list(profiles)
        self._profiles_lock = threading.Lock()
        self._stop_event = threading.Event()

    def set_profiles(self, profiles: Iterable[SellerProfile]) -> None:
        with self._profiles_lock:
            self._profiles = list(profiles)

    def _profile_snapshot(self) -> List[SellerProfile]:
        with self._profiles_lock:
            return list(self._profiles)

    @staticmethod
    def _watcher_seller(profile: SellerProfile) -> dict:
        return {
            "id": profile.seller_id,
            "key": profile.raw_api_key,
            "secret": profile.raw_api_secret,
            "name": profile.name,
            "cargo": profile.preferred_cargo,
        }

    @staticmethod
    def _watcher_options(profile: SellerProfile):
        try:
            width, height = (float(part) for part in profile.label_size.lower().split("x", 1))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid label size for seller {profile.seller_id}: {profile.label_size!r}") from exc

        label = SimpleNamespace(
            w=width,
            h=height,
            shift_y=profile.label_shift_y_mm,
            address=profile.include_address,
            footer=profile.include_footer,
            name_words=1,
            overrides={},
            stamp=profile.print_timestamp,
            show_seller=profile.show_seller_name,
            catalog=str(get_data_path("products.json")),
            no_catalog=False,
            unknown_file=str(get_data_path("unknown_products.json")),
        )
        return SimpleNamespace(
            status=profile.statuses,
            lookback_hours=profile.lookback_hours,
            outsourced_file=str(get_data_path("outsourced_products.txt")),
            mixed=profile.mixed_order_behavior,
            no_switch=not profile.cargo_switch_enabled,
            no_switch_outsourced=profile.no_switch_outsourced,
            dry_run=False,
            print_on_fail=profile.print_on_fail,
            printer=profile.printer_name,
            no_print=not profile.auto_print,
            label=label,
        )

    def run(self):
        setup_logger()
        logger = logging.getLogger("trendyol_manager")
        log_handler = _QtLogHandler(self.log_emitted)
        log_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(log_handler)

        try:
            import trendyol_labels as labels
            import trendyol_watcher as watcher

            self.log_emitted.emit("Order watcher started; seller profiles will be polled automatically.")
            logger.info(
                "Runtime diagnostics: frozen=%s data_dir=%s configured_profiles=%d",
                bool(getattr(sys, "frozen", False)),
                get_data_path(""),
                len(self._profile_snapshot()),
            )
            watcher.tl.register_font()
            state = watcher.load_state()
            attempts = {}
            next_poll = {}
            last_configuration_warning = set()
            no_active_profiles_warning = False

            while not self._stop_event.is_set():
                configured_profiles = [
                    profile for profile in self._profile_snapshot()
                    if profile.is_active and profile.monitoring_enabled
                ]
                if not configured_profiles:
                    if not no_active_profiles_warning:
                        logger.warning(
                            "Watcher idle: no seller profiles are both active and monitoring-enabled."
                        )
                        no_active_profiles_warning = True
                    self._stop_event.wait(1)
                    continue
                no_active_profiles_warning = False

                profiles = []
                for profile in configured_profiles:
                    credential_error = profile.credential_error
                    if not profile.seller_id.isdigit() or credential_error:
                        if profile.seller_id not in last_configuration_warning:
                            reason = credential_error or "Seller ID must contain digits only."
                            self.log_emitted.emit(
                                f"[{profile.display_tag}] Monitoring skipped: {reason}"
                            )
                            last_configuration_warning.add(profile.seller_id)
                        self.status_updated.emit(profile.seller_id, "Configuration Error")
                        continue
                    last_configuration_warning.discard(profile.seller_id)
                    profiles.append(profile)

                sellers = [self._watcher_seller(profile) for profile in profiles]
                labels.set_sellers(sellers)
                now = time.monotonic()

                for profile, seller in zip(profiles, sellers):
                    if self._stop_event.is_set():
                        break
                    sid = profile.seller_id
                    if now < next_poll.get(sid, 0):
                        continue

                    self.status_updated.emit(sid, "Active")
                    try:
                        logger.info(
                            "[%s] Poll started: statuses=%s lookback_hours=%s",
                            profile.display_tag,
                            ",".join(profile.statuses),
                            profile.lookback_hours,
                        )
                        baseline = sid not in state.setdefault("sellers_seen", [])
                        watcher.poll_once(
                            self._watcher_options(profile),
                            state,
                            attempts,
                            seller,
                            baseline_only=baseline,
                            on_processed=self.order_processed.emit,
                        )
                        if baseline:
                            state["sellers_seen"].append(sid)
                            watcher.save_state(state)
                    except SystemExit as exc:
                        logger.error("[%s] Seller API error: %s", profile.display_tag, exc)
                        self.log_emitted.emit(f"[{profile.display_tag}] Seller API error: {exc}")
                        self.status_updated.emit(sid, "Error")
                    except Exception as exc:
                        logger.exception("[%s] Poll failed", profile.display_tag)
                        self.log_emitted.emit(
                            f"[{profile.display_tag}] {type(exc).__name__}: {exc}"
                        )
                        self.status_updated.emit(sid, "Error")

                    next_poll[sid] = time.monotonic() + max(1, profile.polling_interval_seconds)

                self._stop_event.wait(1)
        except (Exception, SystemExit) as exc:
            logger.exception("Watcher failed to initialize or stopped unexpectedly")
            self.log_emitted.emit(f"Watcher stopped: {type(exc).__name__}: {exc}")
        finally:
            logger.info("Order watcher thread stopped.")
            logger.removeHandler(log_handler)

    def stop(self) -> None:
        self._stop_event.set()
