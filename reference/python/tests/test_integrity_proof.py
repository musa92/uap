"""The ad did not change the answer: what is proven, and what is only asserted."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

from uap import Exchange, SigningKey
from uap.integrity import (answer_digest, commit_answer, compose,
                           verify_answer_commitment, verify_composition)
from uap.measurement import assess, meets_mrc
from uap.supply_chain import verify_chain

ANSWER = "Kyoto ryokan rates peak in November for the autumn foliage."
DECISION = {"placements": [{"placement_id": "p1", "click_id": "ck_1", "creative": {
    "content_digest": "sha256:" + "5b" * 32,
    "content": {"brand_name": "Acme", "headline": "Kyoto ryokan",
                "body": "From $180 a night.",
                "actions": [{"type": "link", "label": "See rooms",
                             "url": "https://acme.example/kyoto"}]},
    "disclosure": {"label": "Sponsored", "advertiser_name": "Acme"}}}]}


# -- composition is mechanically checkable by anyone -------------------------

def test_composition_is_exactly_reproducible():
    composed = compose(ANSWER, DECISION)
    ok, why = verify_composition(composed.text, ANSWER, DECISION)
    assert ok, why


def test_an_answer_edited_to_favour_the_advertiser_is_caught():
    composed = compose(ANSWER, DECISION)
    tampered = composed.text.replace("November", "November, and Acme has the best rates")
    ok, why = verify_composition(tampered, ANSWER, DECISION)
    assert not ok and "answer shown differs" in why


def test_creative_woven_into_the_answer_body_is_caught():
    woven = ANSWER + " Try Acme Travel for free cancellation."
    composed = compose(woven, DECISION)
    ok, _ = verify_composition(composed.text, ANSWER, DECISION)
    assert not ok


def test_organic_answer_survives_composition_byte_for_byte():
    composed = compose(ANSWER, DECISION)
    assert composed.organic_answer == ANSWER
    assert composed.organic_answer_digest == answer_digest(ANSWER)


# -- ordering: the commitment precedes selection -----------------------------

def test_commitment_matches_the_rendered_answer():
    commitment = commit_answer(ANSWER, "req_1", "2026-09-02T14:30:00Z")
    composed = compose(ANSWER, DECISION)
    ok, why = verify_answer_commitment(composed.text, commitment.digest)
    assert ok, why


def test_answer_changed_after_commitment_is_detected():
    commitment = commit_answer(ANSWER, "req_1", "2026-09-02T14:30:00Z")
    later = compose(ANSWER.replace("November", "December"), DECISION)
    ok, _ = verify_answer_commitment(later.text, commitment.digest)
    assert not ok


def test_exchange_refuses_a_request_with_no_commitment():
    ux = Exchange("uax.example", SigningKey.generate("k"))
    with pytest.raises(ValueError, match="organic_answer_digest"):
        ux.decide({"id": "r1", "placements": [], "context": {}})


def test_holdout_is_deterministic_and_close_to_the_configured_rate():
    ux = Exchange("uax.example", SigningKey.generate("k"), holdout_rate=0.05)
    picks = [ux._is_holdout(f"req_{i}") for i in range(20000)]
    assert ux._is_holdout("req_7") == ux._is_holdout("req_7")
    assert 0.04 < sum(picks) / len(picks) < 0.06


# -- measurement -------------------------------------------------------------

@pytest.mark.parametrize("view,expected", [
    ({"standard": "mrc_display", "viewable": True, "visible_ms": 3400, "visible_pct": 100}, True),
    ({"standard": "mrc_display", "viewable": True, "visible_ms": 900, "visible_pct": 100}, False),
    ({"standard": "mrc_display", "viewable": True, "visible_ms": 3400, "visible_pct": 40}, False),
    ({"standard": "mrc_video", "viewable": True, "visible_ms": 1500, "visible_pct": 100}, False),
    ({"standard": "delivered_only", "viewable": True, "visible_ms": 9999}, False),
    ({"standard": "mrc_display", "viewable": True}, False),
])
def test_mrc_thresholds(view, expected):
    assert meets_mrc(view)[0] is expected


def test_uniform_dwell_times_are_flagged():
    batch = [{"viewability": {"standard": "mrc_display", "viewable": True,
                              "visible_ms": 3000, "visible_pct": 100,
                              "ivt": {"classification": "valid"}},
              "trust_tier": 1} for _ in range(50)]
    assert any("identical dwell" in a for a in assess(batch).anomalies)


def test_tier_zero_reported_as_valid_is_flagged():
    batch = [{"viewability": {"standard": "delivered_only", "viewable": False,
                              "ivt": {"classification": "valid"}},
              "trust_tier": 0}]
    assert any("tier 0" in a for a in assess(batch).anomalies)


# -- supply chain ------------------------------------------------------------

DECL = {"sellers": [{"seller_id": "node_1", "anchor_type": "model_steward", "trust_tier": 1}]}


def test_valid_chain_resolves():
    chain = {"complete": True, "nodes": [
        {"asi": "uax.example", "sid": "node_1", "hp": 1,
         "anchor": {"type": "model_steward"}, "trust_tier": 1}]}
    v = verify_chain(chain, {"uax.example": DECL})
    assert v.ok and v.resolved == 1 and v.payment_hops == 1


def test_seller_not_in_the_declaration_is_unauthorized():
    chain = {"complete": True, "nodes": [
        {"asi": "uax.example", "sid": "ghost", "hp": 1, "anchor": {"type": "domain"}}]}
    v = verify_chain(chain, {"uax.example": DECL})
    assert not v.ok and any("unauthorized" in r for r in v.reasons)


def test_overclaimed_trust_tier_is_caught():
    chain = {"complete": True, "nodes": [
        {"asi": "uax.example", "sid": "node_1", "hp": 1,
         "anchor": {"type": "model_steward"}, "trust_tier": 2}]}
    v = verify_chain(chain, {"uax.example": DECL})
    assert not v.ok and any("substantiates" in r for r in v.reasons)


def test_incomplete_chain_and_loops_are_rejected():
    hop = {"asi": "uax.example", "sid": "node_1", "hp": 1, "anchor": {"type": "domain"}}
    assert not verify_chain({"complete": False, "nodes": [hop]}, {}).ok
    v = verify_chain({"complete": True, "nodes": [hop, dict(hop)]}, {})
    assert any("loops" in r for r in v.reasons)


def test_chain_with_no_payment_hop_is_rejected():
    chain = {"complete": True, "nodes": [
        {"asi": "uax.example", "sid": "node_1", "hp": 0, "anchor": {"type": "domain"}}]}
    assert not verify_chain(chain, {}).ok


def test_unresolvable_hops_are_reported_not_failed():
    chain = {"complete": True, "nodes": [
        {"asi": "other.example", "sid": "x", "hp": 1, "anchor": {"type": "domain"}}]}
    v = verify_chain(chain, {})
    assert v.ok and v.unresolvable == 1
