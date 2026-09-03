"""Ed25519 signing and detached object signatures.

Two backends. `cryptography`, when installed, provides constant-time signing.
The pure-Python fallback (RFC 8032) exists so the reference implementation can
be vendored into a serving node without adding a dependency to the inference
path; it is not constant-time and is unsuitable for production key handling.

Object signatures are detached and domain-separated. The signing input is

    tag || 0x00 || JCS(object without "signature")

where `tag` names the object type. Without domain separation a signature over
one object type is replayable as another wherever the two share a field subset.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Any

from .canonical import canonicalize

__all__ = [
    "SigningKey", "VerifyingKey", "sign_object", "verify_object",
    "b64u_encode", "b64u_decode", "DOMAINS", "BACKEND",
]

# Domain-separation tags, one per signed object type in the protocol.
DOMAINS = {
    "decision":     b"uap-decision/2026-09-02",
    "receipt":      b"uap-receipt/2026-09-02",
    "bundle":       b"uap-bundle/2026-09-02",
    "bid":          b"uap-bid/2026-09-02",
    "sellers":      b"uap-sellers/2026-09-02",
    "supply_chain": b"uap-supplychain/2026-09-02",
    "settlement":   b"uap-settlement/2026-09-02",
}


def b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64u_decode(text: str) -> bytes:
    if text.endswith("="):
        raise ValueError("base64url MUST be unpadded (RFC 4648 §5)")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --------------------------------------------------------------------------
# Backend selection
# --------------------------------------------------------------------------
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519 as _ed
    from cryptography.hazmat.primitives import serialization as _ser
    BACKEND = "cryptography"
except ImportError:  # pragma: no cover - exercised only without the extra
    _ed = None
    BACKEND = "pure-python"


# --------------------------------------------------------------------------
# Pure-Python Ed25519 (RFC 8032 §5.1). Used only when `cryptography` is absent.
# --------------------------------------------------------------------------
_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _pt_add(P, Q):
    x1, y1, z1, t1 = P
    x2, y2, z2, t2 = Q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    d = 2 * z1 * z2 % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _pt_mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _pt_add(Q, P)
        P = _pt_add(P, P)
        s >>= 1
    return Q


_G_y = 4 * pow(5, _P - 2, _P) % _P
_G_x = None


def _recover_x(y, sign):
    if y >= _P:
        return None
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if xx == 0:
        return None if sign else 0
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = x * _I % _P
    if (x * x - xx) % _P != 0:
        return None
    if x & 1 != sign:
        x = _P - x
    return x


_G_x = _recover_x(_G_y, 0)
_G = (_G_x, _G_y, 1, _G_x * _G_y % _P)


def _compress(P):
    x, y, z, _ = P
    zi = pow(z, _P - 2, _P)
    x, y = x * zi % _P, y * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(b):
    y = int.from_bytes(b, "little")
    sign = (y >> 255) & 1
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _secret_expand(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _pure_public(seed):
    a, _ = _secret_expand(seed)
    return _compress(_pt_mul(a, _G))


def _pure_sign(seed, msg):
    a, prefix = _secret_expand(seed)
    A = _compress(_pt_mul(a, _G))
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), "little") % _L
    R = _compress(_pt_mul(r, _G))
    k = int.from_bytes(hashlib.sha512(R + A + msg).digest(), "little") % _L
    return R + int.to_bytes((r + k * a) % _L, 32, "little")


def _pure_verify(pub, msg, sig):
    if len(sig) != 64 or len(pub) != 32:
        return False
    A = _decompress(pub)
    R = _decompress(sig[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    k = int.from_bytes(hashlib.sha512(sig[:32] + pub + msg).digest(), "little") % _L
    lhs = _pt_mul(s, _G)
    rhs = _pt_add(R, _pt_mul(k, A))
    return _compress(lhs) == _compress(rhs)


# --------------------------------------------------------------------------
# Key objects
# --------------------------------------------------------------------------
class VerifyingKey:
    __slots__ = ("kid", "_raw", "_impl")

    def __init__(self, kid: str, raw: bytes):
        if len(raw) != 32:
            raise ValueError("an Ed25519 public key is 32 bytes")
        self.kid = kid
        self._raw = raw
        self._impl = _ed.Ed25519PublicKey.from_public_bytes(raw) if _ed else None

    @property
    def raw(self) -> bytes:
        return self._raw

    def verify(self, message: bytes, signature: bytes) -> bool:
        if self._impl is not None:
            try:
                self._impl.verify(signature, message)
                return True
            except Exception:
                return False
        return _pure_verify(self._raw, message, signature)

    def to_jwk(self) -> dict:
        return {"kty": "OKP", "crv": "Ed25519", "kid": self.kid,
                "x": b64u_encode(self._raw), "alg": "EdDSA", "use": "sig"}

    @classmethod
    def from_jwk(cls, jwk: dict) -> "VerifyingKey":
        if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
            raise ValueError("expected an OKP/Ed25519 JWK")
        return cls(jwk["kid"], b64u_decode(jwk["x"]))


class SigningKey:
    __slots__ = ("kid", "_seed", "_impl", "_pub")

    def __init__(self, kid: str, seed: bytes):
        if len(seed) != 32:
            raise ValueError("an Ed25519 seed is 32 bytes")
        self.kid = kid
        self._seed = seed
        if _ed:
            self._impl = _ed.Ed25519PrivateKey.from_private_bytes(seed)
            self._pub = self._impl.public_key().public_bytes(
                _ser.Encoding.Raw, _ser.PublicFormat.Raw)
        else:
            self._impl = None
            self._pub = _pure_public(seed)

    @classmethod
    def generate(cls, kid: str) -> "SigningKey":
        return cls(kid, secrets.token_bytes(32))

    @classmethod
    def from_seed_hex(cls, kid: str, seed_hex: str) -> "SigningKey":
        return cls(kid, bytes.fromhex(seed_hex))

    @property
    def verifying_key(self) -> VerifyingKey:
        return VerifyingKey(self.kid, self._pub)

    def sign(self, message: bytes) -> bytes:
        if self._impl is not None:
            return self._impl.sign(message)
        return _pure_sign(self._seed, message)


class KeyRing:
    """Resolves a kid to a verifying key, as a JWKS endpoint would."""

    def __init__(self) -> None:
        self._keys: dict[str, VerifyingKey] = {}

    def add(self, key: VerifyingKey) -> "KeyRing":
        self._keys[key.kid] = key
        return self

    def get(self, kid: str) -> VerifyingKey | None:
        return self._keys.get(kid)

    def to_jwks(self) -> dict:
        return {"keys": [k.to_jwk() for k in self._keys.values()]}


# --------------------------------------------------------------------------
# Detached object signatures
# --------------------------------------------------------------------------
def _signing_input(obj: dict, domain: str) -> bytes:
    if domain not in DOMAINS:
        raise KeyError(f"unknown signature domain {domain!r}")
    body = {k: v for k, v in obj.items() if k != "signature"}
    return DOMAINS[domain] + b"\x00" + canonicalize(body)


def sign_object(obj: dict, key: SigningKey, domain: str, created: str | None = None) -> dict:
    """Return `obj` with a detached `signature` member attached."""
    signature = {"kid": key.kid, "alg": "EdDSA",
                 "value": b64u_encode(key.sign(_signing_input(obj, domain))),
                 "domain": DOMAINS[domain].decode()}
    if created:
        signature["created"] = created
    return {**obj, "signature": signature}


def verify_object(obj: dict, keyring: KeyRing, domain: str) -> tuple[bool, str]:
    """Verify a detached signature. Returns (ok, reason)."""
    sig = obj.get("signature")
    if not isinstance(sig, dict):
        return False, "no signature member"
    if sig.get("alg") != "EdDSA":
        return False, f"unsupported alg {sig.get('alg')!r}"
    key = keyring.get(sig.get("kid", ""))
    if key is None:
        return False, f"kid {sig.get('kid')!r} not enrolled"
    try:
        raw = b64u_decode(sig.get("value", ""))
    except Exception as exc:
        return False, f"malformed signature value: {exc}"
    if not key.verify(_signing_input(obj, domain), raw):
        return False, "signature did not verify"
    return True, "ok"
