"""
Tests for intervals_mcp_server.auth — native OAuth token verification.

Covers the real security logic: a valid JWT (RS256 or Better Auth's EdDSA) yields
an AccessToken with the right claims; tampered / expired / wrong-issuer / wrong-key
/ wrong-audience / subject-less tokens yield None (audience is enforced per
RFC 9068); and build_auth only enables auth when the environment is configured.
"""

import asyncio
import time
import types

import jwt
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from intervals_mcp_server.auth import AuthentikTokenVerifier, _audience_variants, build_auth

ISSUER = "https://auth.example/application/o/x/"
RESOURCE = "https://res.example"


def _keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def _verifier(pub, audience):
    v = AuthentikTokenVerifier("https://jwks.invalid", ISSUER, audience)
    # avoid network: hand the verifier a fake JWKS client returning our public key
    v._jwks = types.SimpleNamespace(  # noqa: SLF001
        get_signing_key_from_jwt=lambda _t: types.SimpleNamespace(key=pub)
    )
    return v


def _token(priv, **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "exp": now + 3600,
        "iat": now,
        "sub": "user-123",
        "scope": "read write",
        "azp": "client-abc",
    }
    claims.update(overrides)
    return jwt.encode(claims, priv, algorithm="RS256")


# --------------------------------------------------------------------------- #
# verify_token
# --------------------------------------------------------------------------- #
def test_valid_token_returns_access_token_with_claims():
    priv, pub = _keypair()
    v = _verifier(pub, [RESOURCE, "client-abc"])
    tok = _token(priv)

    result = asyncio.run(v.verify_token(tok))

    assert result is not None
    assert result.subject == "user-123"
    assert result.client_id == "client-abc"
    assert result.scopes == ["read", "write"]
    assert result.resource == RESOURCE
    assert result.token == tok


def test_expired_token_rejected():
    priv, pub = _keypair()
    v = _verifier(pub, [RESOURCE])
    tok = _token(priv, exp=int(time.time()) - 10)
    assert asyncio.run(v.verify_token(tok)) is None


def test_wrong_audience_rejected():
    # Audience is enforced (RFC 9068): a token minted by the same issuer but for a
    # different resource/audience must be rejected. This closes the confused-deputy
    # / token-replay leg where a token for another resource was accepted at /mcp.
    priv, pub = _keypair()
    v = _verifier(pub, ["https://someone-else"])
    tok = _token(priv, aud="https://some-other-resource")
    assert asyncio.run(v.verify_token(tok)) is None


def test_missing_audience_rejected():
    # ``aud`` is a required claim; a token without it is rejected outright.
    priv, pub = _keypair()
    v = _verifier(pub, [RESOURCE])
    now = int(time.time())
    tok = jwt.encode(
        {"iss": ISSUER, "exp": now + 3600, "iat": now, "sub": "user-123"},
        priv,
        algorithm="RS256",
    )
    assert asyncio.run(v.verify_token(tok)) is None


def test_subjectless_token_rejected():
    # ``sub`` is required: subject-less tokens must be rejected rather than
    # falling through to an env-credential fallback.
    priv, pub = _keypair()
    v = _verifier(pub, [RESOURCE])
    now = int(time.time())
    tok = jwt.encode(
        {"iss": ISSUER, "aud": RESOURCE, "exp": now + 3600, "iat": now},
        priv,
        algorithm="RS256",
    )
    assert asyncio.run(v.verify_token(tok)) is None


def test_eddsa_token_accepted():
    # Better Auth signs access tokens with EdDSA (Ed25519); the verifier must
    # accept them, not just RS256.
    priv = ed25519.Ed25519PrivateKey.generate()
    v = _verifier(priv.public_key(), [RESOURCE])
    now = int(time.time())
    tok = jwt.encode(
        {"iss": ISSUER, "aud": RESOURCE, "exp": now + 3600, "iat": now, "sub": "user-ed"},
        priv,
        algorithm="EdDSA",
    )
    result = asyncio.run(v.verify_token(tok))
    assert result is not None
    assert result.subject == "user-ed"


def test_wrong_issuer_rejected():
    priv, pub = _keypair()
    v = _verifier(pub, [RESOURCE])
    tok = _token(priv, iss="https://evil")
    assert asyncio.run(v.verify_token(tok)) is None


def test_signature_from_other_key_rejected():
    priv, _ = _keypair()
    _, other_pub = _keypair()  # verifier gets a key that did NOT sign the token
    v = _verifier(other_pub, [RESOURCE])
    tok = _token(priv)
    assert asyncio.run(v.verify_token(tok)) is None


def test_missing_required_claim_rejected():
    priv, pub = _keypair()
    v = _verifier(pub, [RESOURCE])
    # drop exp -> options require ["exp",...] -> rejected
    now = int(time.time())
    tok = jwt.encode({"iss": ISSUER, "aud": RESOURCE, "iat": now}, priv, algorithm="RS256")
    assert asyncio.run(v.verify_token(tok)) is None


def test_client_id_falls_back_to_resource_when_no_azp():
    priv, pub = _keypair()
    v = _verifier(pub, [RESOURCE])
    tok = _token(priv, azp=None)
    del_claims = jwt.decode(tok, options={"verify_signature": False})
    assert "azp" in del_claims  # azp present but None
    result = asyncio.run(v.verify_token(tok))
    assert result is not None
    assert result.client_id == RESOURCE  # falls back to the aud/resource


# --------------------------------------------------------------------------- #
# _audience_variants
# --------------------------------------------------------------------------- #
def test_audience_variants_include_both_slash_forms_and_client_id():
    variants = _audience_variants("https://res.example", "cid")
    assert "https://res.example" in variants
    assert "https://res.example/" in variants
    assert "cid" in variants


def test_audience_variants_dedupe_and_no_client_id():
    variants = _audience_variants("https://res.example/", None)
    assert variants == ["https://res.example", "https://res.example/"]


# --------------------------------------------------------------------------- #
# build_auth
# --------------------------------------------------------------------------- #
def test_build_auth_disabled_without_env(monkeypatch):
    for var in ("MCP_ISSUER", "MCP_RESOURCE", "MCP_JWKS_URI", "MCP_CLIENT_ID"):
        monkeypatch.delenv(var, raising=False)
    assert build_auth() == (None, None)


def test_build_auth_enabled_with_env(monkeypatch):
    monkeypatch.setenv("MCP_ISSUER", ISSUER)
    monkeypatch.setenv("MCP_RESOURCE", RESOURCE)
    monkeypatch.setenv("MCP_JWKS_URI", "https://auth.example/jwks/")
    monkeypatch.setenv("MCP_CLIENT_ID", "client-abc")
    settings, verifier = build_auth()
    assert settings is not None
    assert isinstance(verifier, AuthentikTokenVerifier)
    assert str(settings.issuer_url) == ISSUER
    # audience carries both slash forms + client id
    assert "client-abc" in verifier._audience  # noqa: SLF001
