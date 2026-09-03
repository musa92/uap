"""Budget-safe allocation for local decisioning (SPEC.md §8.2, revised).

The open problem in draft-01: bundles sync hourly, a node cannot see that a
campaign exhausted on other nodes, so it serves impressions in good faith that
settle to nothing. Draft-01 said over-delivery "is discarded at settlement",
which puts the loss on the party least able to prevent it.

The rule here inverts that. The exchange allocates each node a slice such that

    sum over nodes of (slice_i x price) <= remaining budget

at the moment the bundle is issued. A node that serves within its slice is
always paid. If every node fills its slice the campaign is exactly spent; if
the exchange over-allocates, that is the exchange's error and the exchange
eats it. Unfilled slices return to the pool at the next issue.

Allocation is proportional to each node's recent verified delivery, floored at
a minimum so new supply gets a ramp, and capped per node so one node cannot
absorb a campaign.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["allocate", "Allocation"]

MIN_SLICE = 10          # every enrolled node gets a ramp
MAX_NODE_SHARE = 0.25   # no single node takes more than a quarter of a period


@dataclass(frozen=True)
class Allocation:
    line_item_id: str
    slices: dict            # entity_id -> impressions
    remaining_budget_micros: int
    price_cpm_micros: int
    allocated_micros: int

    @property
    def utilisation(self) -> float:
        return self.allocated_micros / self.remaining_budget_micros if self.remaining_budget_micros else 0.0


def allocate(line_item: dict, nodes: dict[str, int], *, remaining_budget_micros: int,
             expected_price_cpm_micros: int, period_fraction: float = 1.0) -> Allocation:
    """Split a line item's remaining budget into per-node impression slices.

    nodes: entity_id -> verified impressions delivered in the trailing window.
    period_fraction: share of the remaining flight this bundle covers, so an
                     hourly bundle for a 30-day flight does not hand out the
                     whole budget at once.
    """
    lid = line_item.get("line_item_id", "")
    price = max(1, int(expected_price_cpm_micros))
    budget_now = int(remaining_budget_micros * min(1.0, max(0.0, period_fraction)))
    total_imps = budget_now * 1000 // price
    if total_imps <= 0 or not nodes:
        return Allocation(lid, {}, remaining_budget_micros, price, 0)

    cap = max(MIN_SLICE, int(total_imps * MAX_NODE_SHARE))
    weights = {e: max(1, v) for e, v in nodes.items()}
    wsum = sum(weights.values())

    # Proportional, then clamp to [MIN_SLICE, cap], then trim so the sum never
    # exceeds what the budget covers. Trimming largest-first keeps small nodes'
    # ramps intact.
    slices = {e: max(MIN_SLICE, min(cap, total_imps * w // wsum)) for e, w in weights.items()}
    over = sum(slices.values()) - total_imps
    for e in sorted(slices, key=slices.get, reverse=True):
        if over <= 0:
            break
        cut = min(over, slices[e] - MIN_SLICE)
        slices[e] -= cut
        over -= cut
    if over > 0:                                   # budget cannot even fund the ramps
        for e in sorted(slices, key=slices.get, reverse=True):
            if over <= 0:
                break
            cut = min(over, slices[e])
            slices[e] -= cut
            over -= cut
        slices = {e: s for e, s in slices.items() if s > 0}

    allocated = sum(slices.values()) * price // 1000
    assert allocated <= remaining_budget_micros, "allocation exceeded budget"
    return Allocation(lid, slices, remaining_budget_micros, price, allocated)
