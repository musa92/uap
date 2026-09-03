"""Property-based tests for the code that parses untrusted input.

The canonicalizer and the predicate evaluator both consume data supplied by a
counterparty — a bundle from an exchange, a receipt from a node. Example-based
tests only cover the inputs someone thought of, which is the wrong coverage
model for a parser sitting on a trust boundary.

Hypothesis generates the ones nobody thought of.
"""
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from uap import predicate
from uap.canonical import canonicalize, loads, serialize

SETTINGS = settings(max_examples=300, deadline=None,
                    suppress_health_check=[HealthCheck.too_slow])

# JSON values cspell would call data: no NaN, no infinity, no non-string keys.
json_scalars = st.one_of(
    st.none(), st.booleans(),
    st.integers(min_value=-(2**53), max_value=2**53),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
    st.text(max_size=40),
)
json_values = st.recursive(
    json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=6),
        st.dictionaries(st.text(max_size=12), children, max_size=6)),
    max_leaves=25,
)


# --------------------------------------------------------------------------
# RFC 8785 canonicalization
# --------------------------------------------------------------------------

@given(json_values)
@SETTINGS
def test_canonical_output_is_parseable_json(value):
    """Whatever we emit must be readable by an ordinary JSON parser."""
    assert loads(serialize(value)) is not None or value is None


@given(json_values)
@SETTINGS
def test_canonicalization_is_idempotent(value):
    """Canonicalizing an already-canonical document must not change it."""
    once = serialize(value)
    assert serialize(loads(once)) == once


@given(st.dictionaries(st.text(min_size=1, max_size=10), json_scalars,
                       min_size=2, max_size=8))
@SETTINGS
def test_key_insertion_order_does_not_affect_output(mapping):
    """The property every signature in the protocol depends on.

    Two parties building the same object in different orders must produce
    identical bytes, or every cross-implementation verification fails.
    """
    shuffled = dict(reversed(list(mapping.items())))
    assert canonicalize(mapping) == canonicalize(shuffled)


@given(st.floats(allow_nan=False, allow_infinity=False, width=64))
@SETTINGS
def test_numbers_round_trip_exactly(x):
    """A price that changes when serialized is a settlement bug.

    Compared as floats on purpose. RFC 8785 prints an integral value without a
    decimal point, so 5.042380249996159e16 canonicalizes to
    "50423802499961590" — correct, and what a JavaScript implementation emits.
    Python then parses that back as an arbitrary-precision int, which does not
    compare equal to the original double, while JavaScript parses it back to
    the same double.

    Hypothesis found this on its first run. It is a language artefact rather
    than a canonicalization defect, but it is exactly the kind of thing that
    turns into a cross-implementation digest mismatch, which is why UAP
    requires monetary amounts to be integer micros and never floats.
    """
    assert float(loads(serialize(x))) == x


@given(json_values)
@SETTINGS
def test_canonical_bytes_are_valid_utf8(value):
    canonicalize(value).decode("utf-8")


def test_nan_and_infinity_are_refused():
    """JSON cannot represent them; emitting them silently would be worse."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            serialize(bad)


# --------------------------------------------------------------------------
# Appendix A predicate language
# --------------------------------------------------------------------------

intent_ids = st.sampled_from([
    "travel.accommodation.hotel", "travel.destination.japan",
    "travel.transport.rail", "software.infrastructure.gpu_compute", "home.appliances",
])

leaf_terms = st.one_of(
    st.builds(lambda v: {"intent_any": v}, st.lists(intent_ids, max_size=4)),
    st.builds(lambda v: {"intent_all": v}, st.lists(intent_ids, max_size=3)),
    st.builds(lambda v: {"commercial_intent_gte": v},
              st.floats(0, 1, allow_nan=False, allow_infinity=False)),
    st.builds(lambda v: {"locale_any": v},
              st.lists(st.sampled_from(["en-US", "en-GB", "de-DE"]), max_size=3)),
    st.builds(lambda v: {"surface_any": v},
              st.lists(st.sampled_from(["chat", "voice", "ide"]), max_size=3)),
    st.builds(lambda v: {"turn_bucket_any": v},
              st.lists(st.sampled_from(["0", "1", "2-5", "6+"]), max_size=3)),
    st.builds(lambda v: {"brand_risk_max": v}, st.sampled_from(["low", "medium", "high"])),
    st.builds(lambda v: {"geo_any": v}, st.lists(st.sampled_from(["US", "GB"]), max_size=2)),
    # deliberately unknown operators: the language must fail closed on these
    st.builds(lambda v: {"exec_shell": v}, st.text(max_size=8)),
    st.builds(lambda v: {"regex_match": v}, st.text(max_size=8)),
)

predicates = st.recursive(
    leaf_terms,
    lambda children: st.one_of(
        st.builds(lambda v: {"all": v}, st.lists(children, min_size=1, max_size=4)),
        st.builds(lambda v: {"any": v}, st.lists(children, min_size=1, max_size=4)),
        st.builds(lambda v: {"not": v}, children)),
    max_leaves=12,
)

signals = st.fixed_dictionaries({
    "intents": st.lists(
        st.builds(lambda i, c: {"id": i, "confidence": c}, intent_ids,
                  st.floats(0, 1, allow_nan=False, allow_infinity=False)),
        max_size=5),
    "commercial_intent": st.floats(0, 1, allow_nan=False, allow_infinity=False),
    "locale": st.sampled_from(["en-US", "en-GB", "de-DE", "fr-FR"]),
    "surface_hint": st.sampled_from(["chat", "voice", "ide"]),
    "turn": st.fixed_dictionaries({"index_bucket": st.sampled_from(["0", "1", "2-5", "6+"])}),
    "safety": st.fixed_dictionaries({"brand_risk": st.sampled_from(["low", "medium", "high"])}),
})


@given(predicates, signals)
@SETTINGS
def test_evaluation_always_returns_a_bool_and_never_raises(pred, signal):
    """Evaluation is total. A malformed predicate must not crash a serve path."""
    assert isinstance(predicate.evaluate(pred, signal), bool)


@given(predicates, signals)
@SETTINGS
def test_compiled_matches_interpreted(pred, signal):
    """The compiled path is a second implementation of the same semantics.

    Two implementations that disagree would let a node's local auction diverge
    from the exchange's replay of it, which is a settlement dispute.
    """
    compiled = predicate.compile_predicate(pred)
    assert compiled(predicate.prepare(signal)) == predicate.evaluate(pred, signal)


@given(predicates, signals)
@SETTINGS
def test_prepare_does_not_change_the_answer(pred, signal):
    compiled = predicate.compile_predicate(pred)
    assert compiled(signal) == compiled(predicate.prepare(signal))


@given(predicates)
@SETTINGS
def test_unknown_operators_never_match(pred):
    """Fail closed: an operator the node does not understand cannot widen reach."""
    assert predicate.evaluate({"exec_shell": "rm -rf /"}, {}) is False
    assert predicate.evaluate({"regex_match": ".*"}, {}) is False


@given(signals)
@SETTINGS
def test_empty_signal_matches_nothing_positive(signal):
    """A missing field evaluates its term to False, never True."""
    for term in [{"intent_any": ["travel.accommodation.hotel"]},
                 {"commercial_intent_gte": 0.1},
                 {"locale_any": ["en-US"]},
                 {"geo_any": ["US"]},
                 {"brand_risk_max": "high"}]:
        assert predicate.evaluate(term, {}) is False


@given(st.integers(min_value=9, max_value=30))
@SETTINGS
def test_depth_beyond_the_bound_is_rejected_not_evaluated(depth):
    """Appendix A caps depth at 8. Deeper is refused, and never silently true."""
    pred = {"intent_any": ["travel.accommodation.hotel"]}
    for _ in range(depth):
        pred = {"all": [pred]}
    with pytest.raises(predicate.PredicateError):
        predicate.validate(pred)
    assert predicate.evaluate(pred, {"intents": [{"id": "travel.accommodation.hotel"}]}) is False


@given(st.lists(leaf_terms, min_size=65, max_size=90))
@SETTINGS
def test_term_count_beyond_the_bound_is_rejected(terms):
    """Appendix A caps terms at 64 per line item."""
    with pytest.raises(predicate.PredicateError):
        predicate.validate({"all": terms})
