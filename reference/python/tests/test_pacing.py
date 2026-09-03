"""Budget-safe allocation: a node serving inside its slice is always paid."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from hypothesis import given, settings
from hypothesis import strategies as st

from uap.pacing import MAX_NODE_SHARE, MIN_SLICE, allocate

LI = {"line_item_id": "li_1"}


@given(
    nodes=st.dictionaries(st.text(min_size=1, max_size=6), st.integers(0, 100_000), min_size=1, max_size=40),
    budget=st.integers(0, 10**12),
    price=st.integers(1_000_000, 100_000_000),
    frac=st.floats(0.0, 1.0),
)
@settings(max_examples=400, deadline=None)
def test_allocation_never_exceeds_remaining_budget(nodes, budget, price, frac):
    """The property the whole design rests on."""
    a = allocate(LI, nodes, remaining_budget_micros=budget,
                 expected_price_cpm_micros=price, period_fraction=frac)
    assert a.allocated_micros <= budget
    assert sum(a.slices.values()) * price // 1000 <= budget


@given(
    nodes=st.dictionaries(st.text(min_size=1, max_size=6), st.integers(0, 100_000), min_size=1, max_size=40),
    budget=st.integers(10**9, 10**12),
    price=st.integers(1_000_000, 100_000_000),
)
@settings(max_examples=200, deadline=None)
def test_no_node_takes_more_than_the_cap(nodes, budget, price):
    a = allocate(LI, nodes, remaining_budget_micros=budget, expected_price_cpm_micros=price)
    total = budget * 1000 // price
    cap = max(MIN_SLICE, int(total * MAX_NODE_SHARE))
    assert all(s <= cap for s in a.slices.values())


def test_new_nodes_get_a_ramp_when_budget_allows():
    a = allocate(LI, {"veteran": 100_000, "new": 0},
                 remaining_budget_micros=10**10, expected_price_cpm_micros=40_000_000)
    assert a.slices["new"] == MIN_SLICE
    assert a.slices["veteran"] > a.slices["new"]


def test_allocation_is_proportional_to_verified_delivery():
    a = allocate(LI, {"big": 900, "small": 100},
                 remaining_budget_micros=10**9, expected_price_cpm_micros=1_000_000)
    assert a.slices["big"] > a.slices["small"]


def test_budget_too_small_for_ramps_allocates_what_it_can():
    """Ten nodes, budget for three impressions: nobody gets a phantom slice."""
    a = allocate(LI, {f"n{i}": 0 for i in range(10)},
                 remaining_budget_micros=3_000_000, expected_price_cpm_micros=1_000_000_000)
    assert sum(a.slices.values()) <= 3
    assert a.allocated_micros <= 3_000_000


def test_zero_budget_allocates_nothing():
    a = allocate(LI, {"n1": 500}, remaining_budget_micros=0, expected_price_cpm_micros=10_000_000)
    assert a.slices == {} and a.allocated_micros == 0


def test_exactly_spending_the_budget_is_reachable():
    """If every node fills its slice, the campaign is spent and not overspent."""
    a = allocate(LI, {f"n{i}": 1000 for i in range(8)},
                 remaining_budget_micros=8_000_000_000, expected_price_cpm_micros=10_000_000)
    spent = sum(a.slices.values()) * 10_000_000 // 1000
    assert spent <= 8_000_000_000
    assert spent >= 8_000_000_000 * 0.95     # trimming loses at most rounding


# --------------------------------------------------------------------------
# End to end: the exchange's own allocation is what bounds payment
# --------------------------------------------------------------------------

from uap import Exchange, KeyRing, Node, SigningKey, Surface   # noqa: E402
from uap.integrity import SEPARATOR                             # noqa: E402
from uap.nonce import derive_local_nonce                        # noqa: E402


class _Composed:
    organic_answer_digest = "sha256:" + "c1" * 32
    text = "answer\n\n" + SEPARATOR + "\nBrand"


def _wire(budget_micros):
    ex_key = SigningKey.generate("uax")
    ux = Exchange("uax.example", ex_key, floor_cpm_micros=10_000_000)
    ux.add_line_item({
        "line_item_id": "li_1",
        "advertiser": {"id": "b", "display_name": "B"},
        "pricing": {"model": "cpm", "bid_cpm_micros": 20_000_000},
        "pacing": {"budget_micros": budget_micros},
        "creatives": [{"creative_id": "cr", "content_digest": "sha256:" + "5b" * 32,
                       "content": {"headline": "H", "brand_name": "B"}}]})
    skey = SigningKey.generate("s")
    ux.enrol("node.a", skey.verifying_key, trust_tier=1)
    ux.enrol("node.b", SigningKey.generate("s2").verifying_key, trust_tier=1)
    node = Node("node.a", "m", signing_key=SigningKey.generate("n"),
                exchange_keys=KeyRing().add(ex_key.verifying_key), trust_tier=1)
    bundle = ux.issue_bundle()
    node.load_bundle(bundle)
    node.load_allocation(ux.issue_allocation(bundle["bundle_id"], "node.a", period_fraction=1.0))
    return ux, node, Surface("node.a", skey, trust_tier=1), bundle


def _receipt(node, surface, bundle, index):
    return surface.emit_receipt(
        nonce=derive_local_nonce(bundle["bundle_id"], node.entity_id, "li_1", index),
        decision_id="dc", placement_id="pl", creative_digest="sha256:" + "5b" * 32,
        composed=_Composed(),
        viewability={"rendered": True, "standard": "mrc_display", "viewable": True,
                     "method": "intersection_observer", "visible_ms": 2000},
        auction_trace=[{"line_item_id": "li_1", "ecpm_micros": 20_000_000, "outcome": "won"}],
        local_decision={"bundle_id": bundle["bundle_id"], "line_item_id": "li_1",
                        "impression_index": index})


def test_node_inside_its_allocation_is_paid_and_beyond_it_is_not():
    # USD 1.00 budget at USD 20 CPM = 50 impressions across two nodes.
    ux, node, surface, bundle = _wire(budget_micros=1_000_000)
    my_slice = node._slices["li_1"]
    assert 0 < my_slice < 50, "the slice must be a share, not the whole budget"

    assert ux.verify_receipt(_receipt(node, surface, bundle, 0)).billable
    assert ux.verify_receipt(_receipt(node, surface, bundle, my_slice - 1)).billable
    over = ux.verify_receipt(_receipt(node, surface, bundle, my_slice))
    assert not over.billable and "UAP_PACING_EXCEEDED" in over.reason


def test_allocations_across_nodes_cannot_overspend_the_line_item():
    ux, node, surface, bundle = _wire(budget_micros=1_000_000)
    total = sum(n for (b, e, l), n in ux._allocations.items() if l == "li_1")
    assert total * 20_000_000 // 1000 <= 1_000_000


def test_allocation_for_another_node_is_refused():
    ux, node, surface, bundle = _wire(budget_micros=1_000_000)
    other = ux.issue_allocation(bundle["bundle_id"], "node.b")
    import pytest
    with pytest.raises(ValueError, match="different node"):
        node.load_allocation(other)
