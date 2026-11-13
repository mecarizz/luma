"""Outsourced product classification and fulfillment routing engine.

Provides validated loading of outsourced_products.txt, duplicate/redundant rule detection,
consistent Turkish-aware barcode normalization, and detailed mixed-order reporting.
"""
from __future__ import annotations

import fnmatch
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from core.catalog import normalize_identifier
from core.paths import prune_backups


@dataclass
class RuleValidationReport:
    valid_rules: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    redundant_rules: List[Tuple[str, str]] = field(default_factory=list)  # (redundant, covering_rule)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ClassificationResult:
    kind: str  # "normal" | "outsourced" | "mixed"
    do_print: bool
    do_save: bool
    matched_lines: List[Dict[str, Any]] = field(default_factory=list)
    unmatched_lines: List[Dict[str, Any]] = field(default_factory=list)
    matched_rules: Set[str] = field(default_factory=set)


class OutsourcedClassifier:
    """Evaluates packages against outsourced barcode patterns with validation and caching."""

    def __init__(self, file_path: str = "outsourced_products.txt"):
        self.file_path = file_path
        self._patterns: List[str] = []
        self._last_mtime: float = -1.0
        self.load(force=True)

    def load(self, force: bool = False) -> RuleValidationReport:
        """Load patterns from text file, evaluate syntax, and detect duplicates/redundancies."""
        report = RuleValidationReport()
        if not os.path.exists(self.file_path):
            self._patterns = []
            self._last_mtime = -1.0
            return report

        try:
            mtime = os.path.getmtime(self.file_path)
            if not force and mtime == self._last_mtime:
                return report

            patterns: List[str] = []
            seen: Set[str] = set()

            with open(self.file_path, "r", encoding="utf-8-sig") as f:
                for line_num, raw in enumerate(f, 1):
                    # Strip comments starting with #
                    token = raw.split("#", 1)[0].strip()
                    if not token:
                        continue

                    norm = normalize_identifier(token)

                    # Validate characters (alphanumeric, -, _, ., *)
                    if re.search(r"[^\w\-.*]", norm):
                        report.warnings.append(f"Line {line_num}: Rule '{token}' contains unusual characters.")

                    # Check exact duplicates
                    if norm in seen:
                        report.duplicates.append(norm)
                        continue

                    # Check redundancy (e.g. LHLP* already covers LHLPK)
                    for existing in patterns:
                        if existing.endswith("*") and fnmatch.fnmatchcase(norm, existing):
                            report.redundant_rules.append((norm, existing))
                            break

                    seen.add(norm)
                    patterns.append(norm)

            report.valid_rules = patterns
            self._patterns = patterns
            self._last_mtime = mtime

        except Exception as e:
            report.warnings.append(f"Failed to read '{self.file_path}': {e}")

        return report

    @property
    def patterns(self) -> List[str]:
        self.load()
        return list(self._patterns)

    def add_pattern(self, pattern: str) -> bool:
        """Add a pattern to the outsourced list and persist atomically."""
        self.load()
        norm = normalize_identifier(pattern)
        if not norm or norm in self._patterns:
            return False
        self._patterns.append(norm)
        self.save()
        return True

    def remove_pattern(self, pattern: str) -> bool:
        """Remove a pattern from the outsourced list and persist atomically."""
        self.load()
        norm = normalize_identifier(pattern)
        if norm in self._patterns:
            self._patterns.remove(norm)
            self.save()
            return True
        return False

    def save(self) -> None:
        """Atomically persist patterns to outsourced_products.txt with automated backup."""
        parent = os.path.dirname(self.file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if os.path.exists(self.file_path) and os.path.getsize(self.file_path) > 0:
            backup_dir = os.path.join(parent or ".", "backups")
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            try:
                shutil.copy2(self.file_path, os.path.join(backup_dir, f"outsourced_{ts}.txt"))
                # prune text backups as well
                backups = sorted(
                    [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("outsourced_")],
                    key=os.path.getmtime,
                    reverse=True,
                )
                for old in backups[30:]:
                    try:
                        os.remove(old)
                    except OSError:
                        pass
            except OSError:
                pass

        tmp_path = self.file_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write("# Outsourced products list (barcodes forwarded to third-party suppliers)\n")
            for pat in self._patterns:
                f.write(f"{pat}\n")

        os.replace(tmp_path, self.file_path)
        self._last_mtime = os.path.getmtime(self.file_path)

    def is_outsourced_barcode(self, barcode: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Return (is_outsourced, matching_rule)."""
        self.load()
        norm = normalize_identifier(barcode)
        if not norm or not self._patterns:
            return False, None

        for pat in self._patterns:
            if fnmatch.fnmatchcase(norm, pat):
                return True, pat
        return False, None

    def route_package(self, pkg: Dict[str, Any], mixed_mode: str = "both") -> ClassificationResult:
        """Classify package into normal, outsourced, or mixed with line-by-line attribution."""
        self.load()
        lines = pkg.get("lines") or []
        if not self._patterns or not lines:
            return ClassificationResult(
                kind="normal",
                do_print=True,
                do_save=False,
                unmatched_lines=lines,
            )

        matched: List[Dict[str, Any]] = []
        unmatched: List[Dict[str, Any]] = []
        rules_hit: Set[str] = set()

        for ln in lines:
            bc = ln.get("barcode")
            is_out, rule = self.is_outsourced_barcode(bc)
            if is_out:
                matched.append(ln)
                if rule:
                    rules_hit.add(rule)
            else:
                unmatched.append(ln)

        total_lines = len(lines)
        matched_count = len(matched)

        if matched_count == total_lines:
            kind = "outsourced"
            do_print = False
            do_save = True
        elif matched_count > 0:
            kind = "mixed"
            do_print = mixed_mode in ("both", "print")
            do_save = mixed_mode in ("both", "save")
        else:
            kind = "normal"
            do_print = True
            do_save = False

        return ClassificationResult(
            kind=kind,
            do_print=do_print,
            do_save=do_save,
            matched_lines=matched,
            unmatched_lines=unmatched,
            matched_rules=rules_hit,
        )
