#!/usr/bin/env python3
"""Emit cross-implementation vectors from the Python implementation.

Every UAP signature covers the RFC 8785 canonical bytes of an object. If two
implementations canonicalize differently by even one byte, every signature one
produces fails in the other and the protocol does not interoperate. That is the
highest-consequence disagreement possible between implementations, so it gets
its own vector set rather than being assumed.

Python writes these; reference/typescript/test/interop.test.js reads them and
must reproduce every field independently. Regenerate with `make interop`.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference" / "python"))

from uap import predicate                                 # noqa: E402
from uap.canonical import serialize                       # noqa: E402
from uap.crypto import SigningKey, sign_object            # noqa: E402
from uap.integrity import answer_digest, compose, escape   # noqa: E402

OUT = ROOT / "conformance" / "interop"

# RFC 8032 test vector 1, so both sides start from a key with a published value.
SEED = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"

CANONICAL_CASES = [
    {"name": "keys sorted", "value": {"b": 1, "a": 2}},
    {"name": "nested key order", "value": {"z": [1, {"b": 2, "a": 3}], "y": None}},
    {"name": "utf16 key order", "value": {"\u20ac": "euro", "$": "dollar", "a": 1}},
    {"name": "numbers", "value": [0.1, 1e21, 1e-7, -0.0, 1.0, 333333333.33333329, 0, -5]},
    {"name": "large integers", "value": [2 ** 53 - 1, -(2 ** 53 - 1), 5.042380249996159e16]},
    {"name": "escaped characters", "value": {"s": "a\nb\tc \"quoted\" back\\slash"}},
    {"name": "unicode", "value": {"s": "Kyoto \u4eac\u90fd ryokan \u65c5\u9928"}},
    {"name": "surrogate pair", "value": {"s": "\U0001f5fe map"}},
    {"name": "empty containers", "value": {"a": [], "b": {}, "c": ""}},
    {"name": "booleans and null", "value": [True, False, None]},
    {"name": "deep nesting", "value": {"a": {"b": {"c": {"d": [1, 2, {"e": "f"}]}}}}},
]

SIGNING_CASES = [
    {"name": "decision", "domain": "decision",
     "object": {"decision_id": "dc_01J9", "request_id": "01J9", "nonce": "n_7f3c",
                "placements": [{"placement_id": "pl_1", "click_id": "ck_a91f"}]}},
    {"name": "receipt", "domain": "receipt",
     "object": {"receipt_id": "rc_01J9", "nonce": "n_7f3c", "trust_tier": 1,
                "creative_digest": "sha256:" + "5b" * 32,
                "integrity": {"no_decode_influence": True, "disclosure_rendered": True}}},
    {"name": "bundle", "domain": "bundle",
     "object": {"bundle_id": "bn_2026w36", "floor_cpm_micros": 10000000,
                "line_items": [{"line_item_id": "li_991",
                                "pricing": {"model": "cpm", "bid_cpm_micros": 62000000}}]}},
    {"name": "unicode fields", "domain": "decision",
     "object": {"decision_id": "dc_\u4eac\u90fd", "note": "ryokan \u65c5\u9928"}},
]

ESCAPE_CASES = [
    "Traditional inns from $180 a night, cancel up to 24 hours before arrival.",
    "Book now - 50% off this week",
    "- Free cancellation",
    "# Heading",
    "1. Pick a room",
    "2) Then book",
    "Try **bold** and [link](http://x)",
    "<script>alert(1)</script>",
    "back`tick` and under_score_ and pipe | bar ~tilde~",
]

COMPOSE_CASE = {
    "answer": "Kyoto ryokan rates peak in November for the autumn foliage.",
    "decision": {"placements": [{
        "placement_id": "pl_1", "click_id": "ck_1",
        "creative": {"content_digest": "sha256:" + "5b" * 32,
                     "content": {"brand_name": "Acme Travel",
                                 "headline": "Kyoto ryokan, free cancellation",
                                 "body": "Traditional inns from $180 a night.",
                                 "actions": [{"type": "link", "label": "See rooms",
                                              "url": "https://acme.example/kyoto"}]},
                     "disclosure": {"label": "Sponsored", "advertiser_name": "Acme Travel"}}}]},
}

PREDICATE_SIGNALS = [
    {"intents": [{"id": "travel.accommodation.hotel", "confidence": 0.81}],
     "commercial_intent": 0.74, "locale": "en-US", "surface_hint": "chat",
     "turn": {"index_bucket": "2-5"}, "safety": {"brand_risk": "low"}},
    {"intents": [], "commercial_intent": 0.1, "locale": "de-DE"},
    {},
]

PREDICATE_CASES = [
    {"all": [{"intent_any": ["travel.accommodation.hotel"]}, {"commercial_intent_gte": 0.5}]},
    {"any": [{"locale_any": ["de-DE"]}, {"surface_any": ["chat"]}]},
    {"not": {"intent_any": ["travel.insurance"]}},
    {"all": [{"brand_risk_max": "medium"}, {"turn_bucket_any": ["2-5", "6+"]}]},
    {"exec_shell": "rm -rf /"},
    {"intent_confidence_gte": {"id": "travel.accommodation.hotel", "value": 0.8}},
    {"all": []},
    {"bogus": None},
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    key = SigningKey.from_seed_hex("interop-ed25519-01", SEED)

    canonical = [{"name": c["name"], "value": c["value"], "canonical": serialize(c["value"])}
                 for c in CANONICAL_CASES]

    signing = []
    for c in SIGNING_CASES:
        signed = sign_object(c["object"], key, c["domain"])
        signing.append({"name": c["name"], "domain": c["domain"], "object": c["object"],
                        "signature": signed["signature"]["value"]})

    escapes = [{"input": t, "markdown": escape(t, "markdown")} for t in ESCAPE_CASES]

    composed = compose(COMPOSE_CASE["answer"], COMPOSE_CASE["decision"])
    composition = {**COMPOSE_CASE, "text": composed.text,
                   "organic_answer_digest": composed.organic_answer_digest,
                   "answer_digest": answer_digest(COMPOSE_CASE["answer"])}

    predicates = [{"predicate": p, "signal": s, "expected": predicate.evaluate(p, s)}
                  for p in PREDICATE_CASES for s in PREDICATE_SIGNALS]

    bundle = {
        "_note": ("Generated by scripts/gen_interop_vectors.py from the Python "
                  "implementation. A second implementation must reproduce every "
                  "field independently; see reference/typescript/test/interop.test.js."),
        "seed_hex": SEED,
        "kid": key.kid,
        "public_key_hex": key.verifying_key.raw.hex(),
        "canonical": canonical,
        "signing": signing,
        "escaping": escapes,
        "composition": composition,
        "predicates": predicates,
    }
    path = OUT / "vectors.json"
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n")
    print(f"  wrote {path.relative_to(ROOT)}: {len(canonical)} canonical, "
          f"{len(signing)} signing, {len(escapes)} escaping, {len(predicates)} predicate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
