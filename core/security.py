"""Security utilities for credential encryption at rest and secret masking.

Uses native Windows DPAPI (Data Protection API) via ctypes.windll.crypt32 to
encrypt sensitive Trendyol API keys and secrets with the logged-in user's
Windows credentials.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os
import sys
from typing import Optional


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def encrypt_secret(plaintext: Optional[str]) -> str:
    """Encrypt a secret string at rest using Windows DPAPI.

    Returns string prefixed with 'dpapi:' or the original text if encryption is unavailable.
    """
    if not plaintext:
        return ""
    text_clean = str(plaintext).strip()
    if not text_clean or text_clean.startswith("dpapi:"):
        return text_clean

    if not _is_windows():
        # Fallback for non-windows testing environments
        return "b64:" + base64.b64encode(text_clean.encode("utf-8")).decode("ascii")

    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_bytes = text_clean.encode("utf-8")
        in_blob = DATA_BLOB(
            len(data_bytes),
            ctypes.cast(ctypes.create_string_buffer(data_bytes), ctypes.POINTER(ctypes.c_byte)),
        )
        out_blob = DATA_BLOB()

        # CRYPTPROTECT_UI_FORBIDDEN = 0x01
        flags = 0x01
        success = crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            "TrendyolSecret",
            None,
            None,
            None,
            flags,
            ctypes.byref(out_blob),
        )

        if success:
            encrypted_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            kernel32.LocalFree(out_blob.pbData)
            return "dpapi:" + base64.b64encode(encrypted_bytes).decode("ascii")
    except Exception:
        pass

    return text_clean


def decrypt_secret(ciphertext: Optional[str]) -> str:
    """Decrypt a secret string that was encrypted with DPAPI."""
    if not ciphertext:
        return ""
    cipher_clean = str(ciphertext).strip()

    if cipher_clean.startswith("b64:"):
        try:
            return base64.b64decode(cipher_clean[4:]).decode("utf-8")
        except Exception:
            return cipher_clean

    if not cipher_clean.startswith("dpapi:"):
        return cipher_clean

    if not _is_windows():
        return cipher_clean

    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        raw_bytes = base64.b64decode(cipher_clean[6:])
        in_blob = DATA_BLOB(
            len(raw_bytes),
            ctypes.cast(ctypes.create_string_buffer(raw_bytes), ctypes.POINTER(ctypes.c_byte)),
        )
        out_blob = DATA_BLOB()

        flags = 0x01
        success = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            flags,
            ctypes.byref(out_blob),
        )

        if success:
            decrypted_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            kernel32.LocalFree(out_blob.pbData)
            return decrypted_bytes.decode("utf-8")
    except Exception:
        pass

    return cipher_clean


def mask_secret_for_ui(val: Optional[str]) -> str:
    """Return a masked representation of a secret suitable for UI display."""
    if not val:
        return ""
    decrypted = decrypt_secret(val)
    if len(decrypted) <= 4:
        return "••••"
    return f"{decrypted[:2]}••••••••{decrypted[-2:]}"
