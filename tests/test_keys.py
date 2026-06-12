"""Key storage security tests: nothing key-shaped at rest, logs redacted."""

import json
import logging

import pytest

from backend.keys import KeyStore, RedactionFilter

FAKE_KEY = "sk-admin-abc123def456ghi789jkl012"
FAKE_GOOGLE = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE123"


@pytest.fixture
def store(tmp_path, monkeypatch):
    ks = KeyStore(fallback_dir=tmp_path)
    # force the encrypted-file fallback so tests never touch the real OS keychain
    monkeypatch.setattr(ks, "_keyring_available", lambda: False)
    import keyring

    monkeypatch.setattr(keyring, "get_password", lambda *a: None)
    monkeypatch.setattr(keyring, "set_password", lambda *a: (_ for _ in ()).throw(RuntimeError))
    return ks


def test_roundtrip(store):
    store.set_key("openai", FAKE_KEY)
    assert store.get_key("openai") == FAKE_KEY
    store.delete_key("openai")
    assert store.get_key("openai") is None


def test_no_plaintext_on_disk(store, tmp_path):
    store.set_key("openai", FAKE_KEY)
    store.set_key("gemini", FAKE_GOOGLE)
    for f in tmp_path.rglob("*"):
        if f.is_file():
            blob = f.read_bytes()
            assert FAKE_KEY.encode() not in blob, f"plaintext key found in {f.name}"
            assert FAKE_GOOGLE.encode() not in blob, f"plaintext key found in {f.name}"


def test_encrypted_file_not_json(store, tmp_path):
    store.set_key("openai", FAKE_KEY)
    enc = tmp_path / "keys.enc"
    assert enc.exists()
    with pytest.raises(Exception):
        json.loads(enc.read_bytes())


def test_redaction_filter():
    f = RedactionFilter()
    rec = logging.LogRecord(
        "x", logging.INFO, "", 0, f"calling api with {FAKE_KEY} and {FAKE_GOOGLE}", None, None
    )
    f.filter(rec)
    assert FAKE_KEY not in rec.msg
    assert FAKE_GOOGLE not in rec.msg
    assert "[REDACTED]" in rec.msg
