"""Node-side aggregation and federated updates: what leaves, and how noisy it is.

The claims worth testing here are not "it computes a histogram". They are that
the declared spec is closed, that the per-user bound actually binds, that the
distributed noise lands at the right scale no matter how many nodes split it,
and that no single aggregator can read a node's contribution.
"""
import math
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

from uap.aggregate import (MODULUS, AggregationError, AggregationSpec, LocalAggregator,
                           PrivacyBudget, _polya, reconstruct, release, secret_share,
                           spec_digest)
from uap.federated import (FederatedTrainer, GradientSpec, LinearScorer,
                           average_updates, dequantise, quantise)

SPEC = {
    "dimensions": [
        {"field": "intents", "depth": 2,
         "values": ["travel.accommodation", "travel.transport", "finance.banking"]},
        {"field": "commercial_intent", "buckets": [0.0, 0.3, 0.6, 1.0]},
    ],
    "metrics": ["impressions", "clicks"],
    "contribution_bound": 1, "epsilon": 0.5, "k_floor": 50, "min_participants": 100,
}


@pytest.fixture
def spec():
    return AggregationSpec(SPEC)


def _sig(intent="travel.accommodation.hotel", ci=0.7):
    return {"intents": [{"id": intent}], "commercial_intent": ci}


# -- the spec is closed ------------------------------------------------------

def test_a_field_outside_the_binnable_set_is_refused():
    bad = {**SPEC, "dimensions": [{"field": "raw_text", "values": ["a"]}]}
    with pytest.raises(AggregationError) as e:
        AggregationSpec(bad)
    assert e.value.code == "UAP_AGG_FIELD_NOT_BINNABLE"


def test_a_dimension_without_a_vocabulary_is_refused():
    """An open dimension has unbounded cardinality, so a single rare value
    becomes its own cell and identifies whoever produced it."""
    bad = {**SPEC, "dimensions": [{"field": "locale"}]}
    with pytest.raises(AggregationError) as e:
        AggregationSpec(bad)
    assert e.value.code == "UAP_AGG_OPEN_DIMENSION"


def test_an_undeclared_value_falls_into_other_rather_than_a_new_cell(spec):
    before = spec.cells
    cell = spec.cell(_sig("medical.oncology.treatment", 0.7))
    assert cell is not None and spec.cells == before
    # It lands in the trailing "everything else" slot of the intent dimension.
    assert cell // len(spec.dimensions[1]["buckets"][:-1]) == len(SPEC["dimensions"][0]["values"])


def test_the_digest_pins_what_was_agreed(spec):
    assert spec_digest(SPEC) == spec_digest(dict(reversed(list(SPEC.items()))))
    assert spec_digest(SPEC) != spec_digest({**SPEC, "epsilon": 2.0})


# -- the contribution bound --------------------------------------------------

def test_one_user_cannot_contribute_more_than_the_bound(spec):
    a = LocalAggregator(spec)
    accepted = [a.observe("same-user", _sig()) for _ in range(10)]
    assert sum(accepted) == spec.contribution_bound
    assert a.dropped_over_bound == 10 - spec.contribution_bound
    assert max(a.counts) == spec.contribution_bound


def test_the_bound_is_what_makes_epsilon_mean_anything(spec):
    """Sensitivity is the bound. Without it one user moves the count without limit."""
    a = LocalAggregator(AggregationSpec({**SPEC, "contribution_bound": 3}))
    for _ in range(10):
        a.observe("u1", _sig())
    assert max(a.counts) == 3


def test_a_bound_below_one_is_refused():
    with pytest.raises(AggregationError) as e:
        AggregationSpec({**SPEC, "contribution_bound": 0})
    assert e.value.code == "UAP_AGG_BAD_BOUND"


# -- the noise ---------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 10, 100])
def test_distributed_noise_lands_at_the_same_scale_however_many_nodes_split_it(n):
    """A geometric is infinitely divisible, so n nodes each adding Polya(1/n)
    sum to exactly discrete Laplace. Each node adding full noise would be n
    times too noisy; each adding 1/n of the scale would not be private."""
    rng = random.Random(7)
    eps, sens = 0.5, 1
    p = 1.0 - math.exp(-eps / sens)
    target = 2 * (1 - p) / p ** 2
    sums = [sum(_polya(1.0 / n, p, rng) - _polya(1.0 / n, p, rng) for _ in range(n))
            for _ in range(4000)]
    assert abs(statistics.mean(sums)) < 0.6
    assert 0.75 * target < statistics.variance(sums) < 1.35 * target


def test_a_node_calibrates_to_the_declared_floor_not_a_live_count(spec):
    """Fewer nodes reporting than declared means the sum is under-noised, and a
    node cannot verify how many others showed up."""
    a = LocalAggregator(spec)
    a.observe("u", _sig())
    hi = a.finalise(participants=1, rng=random.Random(1))
    lo = a.finalise(participants=100_000, rng=random.Random(1))
    assert hi == lo          # both clamp to min_participants


# -- secret sharing ----------------------------------------------------------

def test_shares_recombine_exactly(spec):
    a = LocalAggregator(spec)
    for i in range(300):
        a.observe(f"u{i}", _sig())
    v = a.finalise(participants=100)
    assert reconstruct(secret_share(v, 2)) == v
    assert reconstruct(secret_share(v, 3)) == v


def test_one_aggregator_alone_learns_nothing(spec):
    """Each share is uniform over the ring, so a single aggregator holding one
    share cannot distinguish a busy node from an idle one."""
    quiet, busy = LocalAggregator(spec), LocalAggregator(spec)
    for i in range(500):
        busy.observe(f"u{i}", _sig())
    sq = secret_share(quiet.finalise(participants=100), 2)[0]
    sb = secret_share(busy.finalise(participants=100), 2)[0]
    # Both look like draws from the same uniform distribution.
    for s in (sq, sb):
        assert all(0 <= x < MODULUS for x in s)
        assert statistics.mean(s) > MODULUS * 0.2


def test_fewer_than_two_aggregators_is_refused(spec):
    with pytest.raises(AggregationError) as e:
        secret_share([1, 2, 3], 1)
    assert e.value.code == "UAP_AGG_TOO_FEW_AGGREGATORS"


# -- release -----------------------------------------------------------------

def test_cells_below_the_k_floor_are_suppressed(spec):
    out = release([10, 500, 49, 51], spec)
    assert out == [None, 500, None, 51]


# -- the budget --------------------------------------------------------------

def test_the_budget_binds(spec):
    b = PrivacyBudget(per_day=1.0)
    b.spend("cmp_1", "2026-09-04", 0.5)
    b.spend("cmp_1", "2026-09-04", 0.5)
    with pytest.raises(AggregationError) as e:
        b.spend("cmp_1", "2026-09-04", 0.01)
    assert e.value.code == "UAP_PRIVACY_BUDGET_EXHAUSTED"
    assert b.remaining("cmp_1", "2026-09-05") == 1.0     # a new day is a new budget


# -- federated updates -------------------------------------------------------

@pytest.fixture
def gspec(spec):
    return GradientSpec({"model_id": "rank.v1", "clip_norm": 1.0, "epsilon": 1.0,
                         "delta": 1e-6, "min_participants": 100,
                         "learning_rate": 0.5}, spec)


def test_sigma_falls_as_epsilon_rises(gspec, spec):
    loose = GradientSpec({"model_id": "m", "clip_norm": 1.0, "epsilon": 4.0,
                          "delta": 1e-6}, spec)
    assert loose.sigma() < gspec.sigma()


def test_one_user_cannot_dominate_the_gradient(gspec):
    """Per-user clipping is the whole basis of the sensitivity bound."""
    m = LinearScorer.zeros(gspec.dims)
    heavy = FederatedTrainer(m, gspec)
    for _ in range(500):
        heavy.observe("one-user", _sig(), clicked=True)
    raw = dequantise(heavy.emit(participants=10 ** 9, rng=random.Random(0)))
    assert math.sqrt(sum(v * v for v in raw)) <= gspec.clip_norm * 1.05


def test_an_undersized_cohort_is_refused(gspec):
    with pytest.raises(AggregationError) as e:
        average_updates([0] * gspec.dims, 5, LinearScorer.zeros(gspec.dims), gspec)
    assert e.value.code == "UAP_FED_COHORT_TOO_SMALL"


def test_quantisation_round_trips_including_negatives():
    v = [1.5, -2.25, 0.0, -0.001]
    assert all(abs(a - b) < 1e-4 for a, b in zip(dequantise(quantise(v)), v))


def test_the_model_learns_which_context_converts_without_seeing_any_of_it(gspec, spec):
    """The point of the whole mechanism: relevance improves and no node's data,
    nor any single aggregator's view, ever contains a conversation."""
    random.seed(3)
    m = LinearScorer.zeros(gspec.dims)
    for _ in range(6):
        shares = []
        for node in range(120):
            t = FederatedTrainer(m, gspec)
            for u in range(60):
                travel = u % 2 == 0
                sig = _sig("travel.accommodation.hotel" if travel else "finance.banking.loan")
                t.observe(f"n{node}u{u}", sig, clicked=travel and u % 3 == 0)
            shares.append(t.emit(participants=120))
        total = [sum(c) % MODULUS for c in zip(*shares)]
        m = average_updates(total, 120, m, gspec)

    travel = m.score(m.features(_sig("travel.accommodation.hotel"), spec))
    finance = m.score(m.features(_sig("finance.banking.loan"), spec))
    assert travel > finance + 0.2
