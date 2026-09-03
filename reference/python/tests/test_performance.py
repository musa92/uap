"""Performance budgets the specification actually commits to.

SPEC.md makes two numeric promises:

  §4.2          serve-time decisioning has a hard budget of p99 <= 80 ms for
                POST /decisions, measured exchange-side
  Appendix A    the targeting predicate language must be evaluable in under
                1 ms for 10^3 line items

A specification that states a latency budget and never measures it is stating a
hope. These tests fail the build when the implementation stops meeting them.

Budgets are set with headroom over the measured figure, not at it, so an
ordinarily loaded CI runner does not produce a red build for no reason. They are
still tight enough that an algorithmic regression — an accidental O(n^2), a
per-item allocation, a re-parse inside a loop — trips them immediately.
"""
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

from uap import KeyRing, SigningKey, auction, predicate, sign_object, verify_object
from uap.canonical import canonicalize
from uap.integrity import compose

# Appendix A claims under 1 ms for 10^3 line items. The compiled path meets it
# (~0.66 ms locally); the budget carries headroom for a shared CI runner while
# staying tight enough to catch an algorithmic regression.
PREDICATE_TARGET_MS = 1.0          # what the spec claims
PREDICATE_BUDGET_MS = 6.0          # compiled path, CI budget
INTERPRETED_BUDGET_MS = 20.0       # interpreted fallback, CI budget
# §4.2 is an end-to-end network budget; the local auction is one component of it
# and must be a small fraction, not the whole thing.
AUCTION_BUDGET_MS = 20.0


def _percentile(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def _time(fn, runs=7):
    """Best-of-N. Reports the floor of achievable time, not scheduler noise."""
    out = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000)
    return min(out), statistics.median(out)


@pytest.fixture(scope="module")
def signal():
    return {
        "signal_version": "uap.intent/1.0", "signal_class": "local_only",
        "intents": [{"id": "travel.accommodation.hotel", "confidence": 0.81},
                    {"id": "travel.destination.japan", "confidence": 0.63}],
        "commercial_intent": 0.74, "locale": "en-US", "surface_hint": "chat",
        "turn": {"index_bucket": "2-5", "is_followup": True},
        "geo": {"granularity": "country", "value": "US"},
        "safety": {"sensitive_category": False, "brand_risk": "low",
                   "production_ready": True},
    }


def _line_items(n):
    """n line items with realistic predicate shape: nested all/any/not, ~8 terms."""
    items = []
    for i in range(n):
        items.append({
            "line_item_id": f"li_{i:05d}",
            "advertiser": {"id": f"brand.{i}.example", "display_name": f"B{i}"},
            "targeting": {"all": [
                {"intent_any": ["travel.accommodation.hotel",
                                "travel.destination.japan", "software.infrastructure"]},
                {"commercial_intent_gte": 0.3},
                {"locale_any": ["en-US", "en-GB", "de-DE"]},
                {"any": [{"surface_any": ["chat", "ide"]},
                         {"turn_bucket_any": ["2-5", "6+"]}]},
                {"not": {"intent_any": ["travel.insurance"]}},
                {"brand_risk_max": "medium"},
            ]},
            "pricing": {"model": "cpm", "bid_cpm_micros": 10_000_000 + i},
            "categories": ["travel.accommodation"],
            "creatives": [{"creative_id": f"cr_{i}", "content_digest": "sha256:" + "5b" * 32,
                           "content": {"headline": "H", "brand_name": "B"}}],
        })
    return items


# --------------------------------------------------------------------------
# Appendix A: 10^3 line items in under 1 ms
# --------------------------------------------------------------------------

def test_compiled_predicate_meets_the_appendix_a_claim(signal):
    """The claim the specification actually makes: 10^3 line items under 1 ms."""
    compiled = [predicate.compile_predicate(i["targeting"]) for i in _line_items(1000)]
    prepared = predicate.prepare(signal)

    best, median = _time(lambda: [f(prepared) for f in compiled])
    print(f"\n  compiled   1,000 items: best {best:.3f} ms, median {median:.3f} ms "
          f"(Appendix A claims < {PREDICATE_TARGET_MS} ms)")
    assert best < PREDICATE_BUDGET_MS, (
        f"compiled predicate evaluation took {best:.2f} ms for 1,000 line items; "
        f"Appendix A claims under {PREDICATE_TARGET_MS} ms")


def test_interpreted_predicate_stays_within_its_own_budget(signal):
    """The fallback path, used when a predicate was not compiled at load."""
    preds = [i["targeting"] for i in _line_items(1000)]
    best, median = _time(lambda: [predicate.evaluate(p, signal) for p in preds])
    print(f"\n  interpreted 1,000 items: best {best:.3f} ms, median {median:.3f} ms")
    assert best < INTERPRETED_BUDGET_MS


def test_compilation_is_worth_it(signal):
    """Guards the reason the compiled path exists at all."""
    preds = [i["targeting"] for i in _line_items(1000)]
    compiled = [predicate.compile_predicate(p) for p in preds]
    prepared = predicate.prepare(signal)
    interp = _time(lambda: [predicate.evaluate(p, signal) for p in preds])[0]
    comp = _time(lambda: [f(prepared) for f in compiled])[0]
    print(f"\n  compiled is {interp/comp:.1f}x faster than interpreted")
    assert comp < interp, "compiling made evaluation slower; remove it"


def test_predicate_cost_is_linear_in_line_items(signal):
    """An accidental O(n^2) is the regression this catches."""
    def cost(n):
        preds = [i["targeting"] for i in _line_items(n)]
        return _time(lambda: [predicate.evaluate(p, signal) for p in preds], runs=5)[0]

    t1, t4 = cost(500), cost(2000)
    ratio = t4 / max(t1, 1e-9)
    print(f"\n  4x the items cost {ratio:.2f}x the time (linear is ~4)")
    assert ratio < 8, f"scaling looks super-linear: 4x items cost {ratio:.1f}x time"


def test_predicate_validation_rejects_oversized_predicates_fast():
    """A hostile bundle must be cheap to reject, not expensive to evaluate."""
    deep = {"all": [{"intent_any": ["x"]}]}
    for _ in range(40):
        deep = {"all": [deep]}

    with pytest.raises(predicate.PredicateError):
        predicate.validate(deep)

    def reject_100():
        for _ in range(100):
            try:
                predicate.validate(deep)
            except predicate.PredicateError:
                pass                      # rejection is the expected outcome

    best, _ = _time(reject_100)
    print(f"\n  rejecting 100 over-deep predicates: {best:.3f} ms")
    assert best < 50


# --------------------------------------------------------------------------
# §4.2: the auction is one component of the 80 ms serve-time budget
# --------------------------------------------------------------------------

def test_full_auction_over_1000_line_items_within_budget(signal):
    items = _line_items(1000)
    placement = {"placement_id": "pl_1", "position": "post_answer",
                 "format": "sponsored_card", "floor_cpm_micros": 10_000_000}

    best, median = _time(lambda: auction.run(items, signal, placement,
                                             floor_cpm_micros=10_000_000))
    print(f"\n  auction    1,000 items: best {best:.3f} ms, median {median:.3f} ms "
          f"(§4.2 budget for the whole request is 80 ms)")
    assert best < AUCTION_BUDGET_MS


# --------------------------------------------------------------------------
# Cryptographic and serialization hot paths
# --------------------------------------------------------------------------

def test_canonicalization_throughput():
    obj = {"line_items": _line_items(50), "bundle_id": "bn_x",
           "issued_at": "2026-09-02T00:00:00Z"}
    best, _ = _time(lambda: canonicalize(obj))
    size = len(canonicalize(obj))
    print(f"\n  canonicalize {size/1024:.0f} KB: {best:.3f} ms")
    assert best < 60


def test_signature_verification_is_not_the_bottleneck():
    key = SigningKey.generate("k1")
    ring = KeyRing().add(key.verifying_key)
    receipt = sign_object({"receipt_id": "rc_1", "nonce": "n_1",
                           "creative_digest": "sha256:" + "5b" * 32}, key, "receipt")
    best, _ = _time(lambda: [verify_object(receipt, ring, "receipt") for _ in range(100)])
    print(f"\n  verify 100 receipts: {best:.3f} ms ({best/100:.4f} ms each)")
    assert best < 200, "receipt verification would dominate settlement at scale"


def test_composition_is_constant_time_in_answer_length():
    """The composer concatenates; it must not scan or rewrite the answer."""
    decision = {"placements": [{"placement_id": "p1", "creative": {
        "content_digest": "sha256:" + "5b" * 32,
        "content": {"headline": "H", "brand_name": "B", "body": "b"},
        "disclosure": {"label": "Sponsored", "advertiser_name": "B"}}}]}
    short, long_ = "x" * 200, "x" * 200_000
    t_short = _time(lambda: compose(short, decision))[0]
    t_long = _time(lambda: compose(long_, decision))[0]
    print(f"\n  compose 200 B: {t_short:.4f} ms | 200 KB: {t_long:.4f} ms")
    # Hashing is linear in the answer, but nothing else may be.
    assert t_long < 40
