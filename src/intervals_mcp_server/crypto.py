"""
Symmetric encryption for user secrets (the per-user Intervals.icu API key).

Uses AES-256-GCM (authenticated encryption). The key is supplied as a
base64-encoded 32-byte value via the ``INTERVALS_ENC_KEY`` environment variable
(mounted from a Kubernetes secret) and is shared by the MCP server and the UI
service so both can read/write the same ciphertext.

Ciphertext layout: ``nonce(12 bytes) || ciphertext+tag``. A fresh random nonce is
used per encryption, so encrypting the same plaintext twice yields different bytes.
The API key must be recoverable (the server uses it to call Intervals), so this is
reversible encryption, not hashing.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LEN = 12
_KEY_LEN = 32


class CryptoError(Exception):
    """Raised when encryption is misconfigured or a payload cannot be decrypted."""


def load_key(raw: str | None = None) -> bytes:
    """Return the 32-byte AES key from a base64 string (or ``INTERVALS_ENC_KEY``)."""
    raw = raw if raw is not None else os.environ.get("INTERVALS_ENC_KEY")
    if not raw:
        raise CryptoError("INTERVALS_ENC_KEY is not set")
    try:
        key = base64.b64decode(raw, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise CryptoError("INTERVALS_ENC_KEY is not valid base64") from exc
    if len(key) != _KEY_LEN:
        raise CryptoError(f"INTERVALS_ENC_KEY must decode to {_KEY_LEN} bytes, got {len(key)}")
    return key


def encrypt(plaintext: str, key: bytes | None = None) -> bytes:
    """Encrypt a string; returns ``nonce || ciphertext``."""
    key = key if key is not None else load_key()
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt(blob: bytes, key: bytes | None = None) -> str:
    """Decrypt bytes produced by :func:`encrypt`. Raises CryptoError on tamper/wrong key."""
    key = key if key is not None else load_key()
    if len(blob) <= _NONCE_LEN:
        raise CryptoError("ciphertext too short")
    nonce, ciphertext = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - InvalidTag etc.
        raise CryptoError("could not decrypt payload") from exc


def generate_key_b64() -> str:
    """Generate a fresh base64-encoded 32-byte key (for provisioning the secret)."""
    return base64.b64encode(os.urandom(_KEY_LEN)).decode("ascii")
