"""Profile L nonce derivation and exchange-side reconstruction."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

from uap import Exchange, KeyRing, Node, SigningKey, Surface
from uap.integrity import SEPARATOR
from uap.nonce import derive_local_nonce


def test_derivation_is_deterministic_and_bound_to_every_input():
    base = derive_local_nonce("bn_a", "node.example", "li_1", 0)
    assert base == derive_local_nonce("bn_a", "node.example", "li_1", 0)
    assert base != derive_local_nonce("bn_b", "node.example", "li_1", 0)
    assert base != derive_local_nonce("bn_a", "other.example", "li_1", 0)
    assert base != derive_local_nonce("bn_a", "node.example", "li_2", 0)
    assert base != derive_local_nonce("bn_a", "node.example", "li_1", 1)


def test_negative_index_rejected():
    with pytest.raises(ValueError):
        derive_local_nonce("bn_a", "node.example", "li_1", -1)


@pytest.fixture
def wired():
    ex_key = SigningKey.generate("uax-1")
    ux = Exchange("uax.example", ex_key, floor_cpm_micros=10_000_000)
    ux.add_line_item({
        "line_item_id": "li_991",
        "advertiser": {"id": "brand.a", "display_name": "A"},
        "targeting": {"all": [{"intent_any": ["travel.accommodation.hotel"]}]},
        "pricing": {"model": "cpm", "bid_cpm_micros": 62_000_000},
        "pacing": {"node_share_impressions": 5},
        "creatives": [{"creative_id": "cr_1", "content_digest": "sha256:" + "5b" * 32,
                       "content": {"headline": "H", "brand_name": "A"}}]})
    surface_key = SigningKey.generate("surface-1")
    ux.enrol("node.example", surface_key.verifying_key, trust_tier=1)
    node = Node("node.example", "hf:test/model", signing_key=SigningKey.generate("n"),
                exchange_keys=KeyRing().add(ex_key.verifying_key), trust_tier=1)
    node.load_bundle(ux.issue_bundle())
    return ux, node, Surface("node.example", surface_key, trust_tier=1)


class _Composed:
    """A composed turn that carries a rendered disclosure.

    Built directly rather than through compose() so a test can vary one input
    without also having to build a full decision.
    """
    organic_answer_digest = "sha256:" + "c1" * 32
    text = "answer text\n\n" + SEPARATOR + "\nBrand - Headline"


TRACE = [{"line_item_id": "li_991", "ecpm_micros": 62_000_000, "outcome": "won"},
         {"line_item_id": "li_310", "ecpm_micros": 41_000_000, "outcome": "lost"}]


def _receipt(node, surface, *, index=None, nonce=None, local=None):
    """Sign a complete Profile L receipt. Every field is set before signing."""
    if local is None:
        local = node.local_decision("li_991")
        if index is not None:
            local = dict(local, impression_index=index,
                         nonce=derive_local_nonce(local["bundle_id"], node.entity_id,
                                                  "li_991", index))
    return surface.emit_receipt(
        nonce=nonce or local["nonce"], decision_id="dc_1", placement_id="pl_1",
        creative_digest="sha256:" + "5b" * 32, composed=_Composed(),
        viewability={"rendered": True, "standard": "mrc_display", "viewable": True,
                     "method": "intersection_observer", "visible_ms": 3400},
        auction_trace=TRACE, local_decision=local)


def test_local_receipt_verifies_without_pre_registration(wired):
    ux, node, surface = wired
    verdict = ux.verify_receipt(_receipt(node, surface))
    assert verdict.billable, verdict.reason


def test_exchange_derives_the_clearing_price_not_the_node(wired):
    ux, node, surface = wired
    verdict = ux.verify_receipt(_receipt(node, surface))
    # Second price is the highest losing eCPM plus one micro, per thousand.
    assert verdict.gross_micros == (41_000_000 + 1) // 1000


def test_nonce_that_does_not_derive_is_rejected(wired):
    ux, node, surface = wired
    r = _receipt(node, surface, nonce="n_" + "0" * 32)
    verdict = ux.verify_receipt(r)
    assert not verdict.billable and "does not derive" in verdict.reason


def test_index_beyond_pacing_allocation_is_rejected(wired):
    ux, node, surface = wired
    verdict = ux.verify_receipt(_receipt(node, surface, index=99))
    assert not verdict.billable and "UAP_PACING_EXCEEDED" in verdict.reason


def test_derived_nonce_is_single_use(wired):
    ux, node, surface = wired
    assert ux.verify_receipt(_receipt(node, surface, index=0)).billable
    replay = ux.verify_receipt(_receipt(node, surface, index=0))
    assert not replay.billable and "UAP_NONCE_SPENT" in replay.reason


def test_node_cannot_derive_for_an_entity_it_is_not_enrolled_as(wired):
    """The entity comes from the signing key, not from anything the node sends."""
    ux, node, surface = wired
    local = {"bundle_id": node.bundle["bundle_id"], "line_item_id": "li_991",
             "impression_index": 0}
    forged = derive_local_nonce(local["bundle_id"], "someone.else", "li_991", 0)
    verdict = ux.verify_receipt(_receipt(node, surface, nonce=forged, local=local))
    assert not verdict.billable and "does not derive" in verdict.reason


def test_unknown_bundle_is_rejected(wired):
    ux, node, surface = wired
    node.bundle = dict(node.bundle, bundle_id="bn_never_issued")
    verdict = ux.verify_receipt(_receipt(node, surface))
    assert not verdict.billable and "unknown bundle" in verdict.reason


# ---------------------------------------------------------------------------
# Fail-closed sensitivity gate (source/taxonomy/sensitive-1.0.json)
# ---------------------------------------------------------------------------

from uap import KeywordClassifier   # noqa: E402


def _node(**kw):
    return Node("n", "m", signing_key=SigningKey.generate("k"),
                exchange_keys=KeyRing(), **kw)


@pytest.mark.parametrize("text", [
    "I have symptoms of depression",
    "facing eviction and debt collectors",
    "do I need a lawyer, I was arrested",
    "questions about my asylum application",
])
def test_detected_sensitive_turns_are_suppressed(text):
    signal = KeywordClassifier().derive([{"role": "user", "content": text}])
    assert signal["safety"]["sensitive_category"] is True
    assert _node(accept_unverified_classifier=True).may_monetise(signal) is False


def test_unrecognised_turn_is_unknown_not_safe():
    """The defect this test exists for: 'no keyword matched' is not 'not sensitive'."""
    signal = KeywordClassifier().derive([{"role": "user", "content": "capital of Peru"}])
    assert signal["safety"]["sensitive_category"] is None
    assert _node(accept_unverified_classifier=True).may_monetise(signal) is False


def test_unverified_classifier_is_refused_by_default():
    signal = KeywordClassifier().derive([{"role": "user", "content": "book a hotel"}])
    signal["safety"]["sensitive_category"] = False      # pretend it could decide
    assert _node().may_monetise(signal) is False
    assert _node(accept_unverified_classifier=True).may_monetise(signal) is True


def test_missing_or_malformed_safety_block_fails_closed():
    node = _node(accept_unverified_classifier=True)
    assert node.may_monetise({}) is False
    assert node.may_monetise({"safety": None}) is False
    assert node.may_monetise({"safety": {}}) is False


def test_production_classifier_needs_no_opt_in():
    class Verified(KeywordClassifier):
        production_ready = True
        classifier_id = "com.example.classifier.v3"

    signal = Verified().derive([{"role": "user", "content": "book a hotel"}])
    signal["safety"]["sensitive_category"] = False
    assert _node().may_monetise(signal) is True
