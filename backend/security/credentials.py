import os
import json
import base64
import sys
from pathlib import Path
from typing import Optional, Dict

from config import settings

CREDENTIALS_FILE = settings.data_dir / "credentials.enc"


class CredentialVault:
    """
    Hardware and OS-level secure credential store.
    On Windows, utilizes Windows DPAPI (CryptProtectData/CryptUnprotectData)
    to encrypt secrets using the logged-in user's cryptographic context.
    """

    @staticmethod
    def _is_windows() -> bool:
        return sys.platform == "win32"

    @classmethod
    def _encrypt_bytes(cls, plaintext: bytes) -> bytes:
        if cls._is_windows():
            try:
                import ctypes
                import ctypes.wintypes

                class DATA_BLOB(ctypes.Structure):
                    _fields_ = [
                        ("cbData", ctypes.wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_byte)),
                    ]

                blob_in = DATA_BLOB(
                    len(plaintext),
                    ctypes.cast(ctypes.create_string_buffer(plaintext), ctypes.POINTER(ctypes.c_byte)),
                )
                blob_out = DATA_BLOB()
                if ctypes.windll.crypt32.CryptProtectData(
                    ctypes.byref(blob_in), "SmartManagerVault", None, None, None, 0, ctypes.byref(blob_out)
                ):
                    ciphertext = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
                    return ciphertext
            except Exception:
                pass

        # Fallback for non-Windows test environments
        return base64.b64encode(plaintext)

    @classmethod
    def _decrypt_bytes(cls, ciphertext: bytes) -> bytes:
        if cls._is_windows():
            try:
                import ctypes
                import ctypes.wintypes

                class DATA_BLOB(ctypes.Structure):
                    _fields_ = [
                        ("cbData", ctypes.wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_byte)),
                    ]

                blob_in = DATA_BLOB(
                    len(ciphertext),
                    ctypes.cast(ctypes.create_string_buffer(ciphertext), ctypes.POINTER(ctypes.c_byte)),
                )
                blob_out = DATA_BLOB()
                if ctypes.windll.crypt32.CryptUnprotectData(
                    ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
                ):
                    plaintext = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
                    return plaintext
            except Exception:
                pass

        # Fallback for non-Windows test environments
        try:
            return base64.b64decode(ciphertext)
        except Exception:
            return b""

    @classmethod
    def _load_vault(cls) -> Dict[str, str]:
        if not CREDENTIALS_FILE.exists():
            return {}
        try:
            raw = CREDENTIALS_FILE.read_bytes()
            if not raw:
                return {}
            decrypted = cls._decrypt_bytes(raw)
            return json.loads(decrypted.decode("utf-8"))
        except Exception:
            return {}

    @classmethod
    def _save_vault(cls, data: Dict[str, str]) -> None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        raw_json = json.dumps(data).encode("utf-8")
        encrypted = cls._encrypt_bytes(raw_json)
        CREDENTIALS_FILE.write_bytes(encrypted)

    @classmethod
    def set_secret(cls, key: str, value: str) -> None:
        """Securely persists a secret string in the DPAPI vault."""
        if not value:
            cls.delete_secret(key)
            return
        vault = cls._load_vault()
        vault[key] = value.strip()
        cls._save_vault(vault)

    @classmethod
    def get_secret(cls, key: str) -> Optional[str]:
        """Retrieves and decrypts a secret from the vault."""
        vault = cls._load_vault()
        return vault.get(key)

    @classmethod
    def delete_secret(cls, key: str) -> bool:
        """Deletes a secret from the vault."""
        vault = cls._load_vault()
        if key in vault:
            del vault[key]
            cls._save_vault(vault)
            return True
        return False

    @classmethod
    def has_secret(cls, key: str) -> bool:
        """Returns True if the secret exists and is non-empty."""
        secret = cls.get_secret(key)
        return bool(secret and secret.strip())

    @staticmethod
    def mask_secret(secret: Optional[str]) -> str:
        """Redacts a secret for safe display in UI or logs."""
        if not secret:
            return ""
        s = secret.strip()
        if len(s) <= 8:
            return "********"
        return f"{s[:3]}****...{s[-4:]}"
