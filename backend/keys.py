"""API key storage.

Order of preference:
1. OS keychain via `keyring` (macOS Keychain, Windows Credential Manager,
   Linux Secret Service).
2. Fallback: Fernet-encrypted file at ~/.burnmeter/keys.enc. The Fernet key is
   generated once and itself stored in the OS keychain; if no keychain backend
   exists at all, the Fernet key lives in a 0600-permission file next to it
   (documented limitation, still never plaintext API keys on disk).

Keys are never written to SQLite or logs. `RedactionFilter` scrubs anything
that looks like a provider key from every log record as defense in depth.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import keyring
from keyring.errors import KeyringError
from cryptography.fernet import Fernet

SERVICE = "burnmeter"
FALLBACK_DIR = Path(os.environ.get("BURNMETER_HOME", "~/.burnmeter")).expanduser()

# OpenAI keys (sk-..., sk-admin-..., sk-proj-...), Google AIza..., generic long bearer-ish tokens
KEY_PATTERNS = re.compile(
    r"(sk-[A-Za-z0-9_-]{10,}|AIza[A-Za-z0-9_-]{10,})"
)


class RedactionFilter(logging.Filter):
    """Logging filter that redacts API-key-shaped strings everywhere."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = KEY_PATTERNS.sub("[REDACTED]", str(record.msg))
        if record.args:
            record.args = tuple(
                KEY_PATTERNS.sub("[REDACTED]", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def install_redaction(logger: logging.Logger | None = None) -> None:
    target = logger or logging.getLogger()
    target.addFilter(RedactionFilter())
    for h in target.handlers:
        h.addFilter(RedactionFilter())


class KeyStore:
    def __init__(self, fallback_dir: Path = FALLBACK_DIR):
        self.fallback_dir = fallback_dir
        self._keyring_ok: bool | None = None

    # -- backend detection ----------------------------------------------------

    def _keyring_available(self) -> bool:
        if self._keyring_ok is None:
            try:
                keyring.set_password(SERVICE, "__probe__", "1")
                keyring.delete_password(SERVICE, "__probe__")
                self._keyring_ok = True
            except (KeyringError, Exception):
                self._keyring_ok = False
        return self._keyring_ok

    # -- fernet fallback --------------------------------------------------------

    def _fernet(self) -> Fernet:
        self.fallback_dir.mkdir(parents=True, exist_ok=True)
        secret: str | None = None
        try:
            secret = keyring.get_password(SERVICE, "__fernet__")
        except Exception:
            secret = None
        if secret is None:
            secret_file = self.fallback_dir / "fernet.key"
            if secret_file.exists():
                secret = secret_file.read_text().strip()
            else:
                secret = Fernet.generate_key().decode()
                try:
                    keyring.set_password(SERVICE, "__fernet__", secret)
                except Exception:
                    secret_file.touch(mode=0o600)
                    secret_file.write_text(secret)
                    secret_file.chmod(0o600)
        return Fernet(secret.encode())

    def _fallback_load(self) -> dict[str, str]:
        f = self.fallback_dir / "keys.enc"
        if not f.exists():
            return {}
        return json.loads(self._fernet().decrypt(f.read_bytes()).decode())

    def _fallback_save(self, data: dict[str, str]) -> None:
        self.fallback_dir.mkdir(parents=True, exist_ok=True)
        f = self.fallback_dir / "keys.enc"
        f.write_bytes(self._fernet().encrypt(json.dumps(data).encode()))
        f.chmod(0o600)

    # -- public API -------------------------------------------------------------

    def set_key(self, provider: str, key: str) -> None:
        if self._keyring_available():
            keyring.set_password(SERVICE, provider, key)
        else:
            data = self._fallback_load()
            data[provider] = key
            self._fallback_save(data)

    def get_key(self, provider: str) -> str | None:
        if self._keyring_available():
            try:
                return keyring.get_password(SERVICE, provider)
            except KeyringError:
                return None
        return self._fallback_load().get(provider)

    def delete_key(self, provider: str) -> None:
        if self._keyring_available():
            try:
                keyring.delete_password(SERVICE, provider)
            except KeyringError:
                pass
        else:
            data = self._fallback_load()
            data.pop(provider, None)
            self._fallback_save(data)
