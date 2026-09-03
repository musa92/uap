"""Ed25519 backend equivalence and RFC 8032 conformance."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import uap.crypto as c
from uap.crypto import SigningKey, VerifyingKey, KeyRing, sign_object, verify_object

# RFC 8032 §7.1, Test 1.
SEED = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
PUB = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
SIG = ("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555"
       "fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")


def test_rfc8032_vector_accelerated():
    k = SigningKey.from_seed_hex("k1", SEED)
    assert k.verifying_key.raw.hex() == PUB
    assert k.sign(b"").hex() == SIG


def test_rfc8032_vector_pure_python(monkeypatch):
    monkeypatch.setattr(c, "_ed", None)
    k = SigningKey.from_seed_hex("k1", SEED)
    assert k.verifying_key.raw.hex() == PUB
    assert k.sign(b"").hex() == SIG
    assert VerifyingKey("k1", bytes.fromhex(PUB)).verify(b"", bytes.fromhex(SIG))


def test_domain_separation_blocks_cross_type_replay():
    k = SigningKey.generate("uax-1")
    ring = KeyRing().add(k.verifying_key)
    signed = sign_object({"decision_id": "dc_1", "nonce": "n_1"}, k, "decision")
    assert verify_object(signed, ring, "decision")[0] is True
    assert verify_object(signed, ring, "bundle")[0] is False


def test_tamper_is_detected():
    k = SigningKey.generate("uax-1")
    ring = KeyRing().add(k.verifying_key)
    signed = sign_object({"decision_id": "dc_1", "nonce": "n_1"}, k, "decision")
    assert verify_object({**signed, "nonce": "n_2"}, ring, "decision")[0] is False


def test_unenrolled_key_is_tier_zero():
    ring = KeyRing().add(SigningKey.generate("enrolled").verifying_key)
    stranger = SigningKey.generate("stranger")
    signed = sign_object({"decision_id": "dc_1"}, stranger, "decision")
    ok, reason = verify_object(signed, ring, "decision")
    assert ok is False and "not enrolled" in reason


def test_padded_base64url_is_rejected():
    k = SigningKey.generate("uax-1")
    ring = KeyRing().add(k.verifying_key)
    signed = sign_object({"a": 1}, k, "decision")
    signed["signature"]["value"] += "="
    assert verify_object(signed, ring, "decision")[0] is False
