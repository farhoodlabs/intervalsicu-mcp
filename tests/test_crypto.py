"""
Tests for intervals_mcp_server.crypto (AES-256-GCM for the user API key).

Covers round-trip, per-message nonce randomness, tamper/wrong-key detection,
and key loading/validation from the environment.
"""

import base64

import pytest

from intervals_mcp_server import crypto
from intervals_mcp_server.crypto import CryptoError

KEY = crypto.load_key(crypto.generate_key_b64())


def test_roundtrip():
    assert crypto.decrypt(crypto.encrypt("s3cr3t-api-key", KEY), KEY) == "s3cr3t-api-key"


def test_same_plaintext_encrypts_differently():
    a = crypto.encrypt("same", KEY)
    b = crypto.encrypt("same", KEY)
    assert a != b  # random nonce per message
    assert crypto.decrypt(a, KEY) == crypto.decrypt(b, KEY) == "same"


def test_ciphertext_does_not_contain_plaintext():
    assert b"api-key" not in crypto.encrypt("my-api-key", KEY)


def test_wrong_key_rejected():
    blob = crypto.encrypt("x", KEY)
    with pytest.raises(CryptoError):
        crypto.decrypt(blob, crypto.load_key(crypto.generate_key_b64()))


def test_tampered_ciphertext_rejected():
    blob = bytearray(crypto.encrypt("x", KEY))
    blob[-1] ^= 0x01  # flip a bit in the GCM tag
    with pytest.raises(CryptoError):
        crypto.decrypt(bytes(blob), KEY)


def test_short_ciphertext_rejected():
    with pytest.raises(CryptoError):
        crypto.decrypt(b"tiny", KEY)


def test_load_key_from_env(monkeypatch):
    monkeypatch.setenv("INTERVALS_ENC_KEY", crypto.generate_key_b64())
    assert len(crypto.load_key()) == 32


def test_load_key_missing(monkeypatch):
    monkeypatch.delenv("INTERVALS_ENC_KEY", raising=False)
    with pytest.raises(CryptoError):
        crypto.load_key()


def test_load_key_wrong_length():
    with pytest.raises(CryptoError):
        crypto.load_key(base64.b64encode(b"too-short").decode())


def test_load_key_bad_base64():
    with pytest.raises(CryptoError):
        crypto.load_key("!!!not-base64!!!")


def test_encrypt_defaults_to_env_key(monkeypatch):
    monkeypatch.setenv("INTERVALS_ENC_KEY", crypto.generate_key_b64())
    assert crypto.decrypt(crypto.encrypt("hello")) == "hello"
