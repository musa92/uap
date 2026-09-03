"""Auction mechanics (SPEC.md §8.4).

Identical semantics in the hosted, local, and hybrid profiles so that revenue is
comparable across them. The elimination order is fixed because the exchange
replays a local auction from the signed bundle and the reported trace; a
different order produces a different trace and a false fraud signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from . import predicate as pred

__all__ = ["AuctionResult", "TraceEntry", "run"]

# Fixed evaluation order. Earlier stages are cheaper and eliminate more.
OUTCOMES = ("eliminated_policy", "eliminated_targeting", "eliminated_frequency",
            "eliminated_pacing", "eliminated_floor", "lost", "won")


@dataclass(frozen=True)
class TraceEntry:
    line_item_id: str
    ecpm_micros: int
    outcome: str

    def to_json(self) -> dict:
        return {"line_item_id": self.line_item_id,
                "ecpm_micros": self.ecpm_micros, "outcome": self.outcome}


@dataclass
class AuctionResult:
    winner: dict | None
    clearing_price_micros: int
    mechanism: str
    trace: list[TraceEntry] = field(default_factory=list)

    def trace_json(self) -> list[dict]:
        return [t.to_json() for t in self.trace]


def normalize_ecpm(pricing: dict, p_ctr: float, p_cvr: float) -> int:
    """Normalize any pricing model to eCPM in micros.

    eCPM = bid_cpc * pCTR * 1000 ; eCPM = bid_cpa * pCVR * 1000.
    The exchange publishes the model version used, in the clearing block.
    """
    model = pricing.get("model")
    if model == "cpm":
        return int(pricing.get("bid_cpm_micros", 0))
    if model == "cpc":
        return int(pricing.get("bid_cpc_micros", 0) * p_ctr * 1000)
    if model == "cpa":
        return int(pricing.get("bid_cpa_micros", 0) * p_cvr * 1000)
    return 0


def _policy_ok(item: dict, policy: dict, placement: dict, steward: dict | None) -> bool:
    adv = (item.get("advertiser") or {}).get("id")
    if adv in set(policy.get("blocked_advertisers") or []):
        return False
    cats = set(item.get("categories") or [])
    if cats & set(policy.get("blocked_categories") or []):
        return False
    allowed = policy.get("allowed_formats")
    fmt = placement.get("format")
    if allowed and fmt not in allowed:
        return False
    if steward:
        ap = steward.get("advertising_policy") or {}
        if not ap.get("permitted", False):
            return False
        if ap.get("permitted_positions") and placement.get("position") not in ap["permitted_positions"]:
            return False
        if ap.get("permitted_formats") and fmt not in ap["permitted_formats"]:
            return False
        if cats & set(ap.get("blocked_categories") or []):
            return False
    return True


def run(line_items: Iterable[dict], signal: dict, placement: dict, *,
        policy: dict | None = None, steward_policy: dict | None = None,
        floor_cpm_micros: int = 0, mechanism: str = "uap.auction.second_price",
        p_ctr: float = 0.01, p_cvr: float = 0.001,
        frequency_state: dict | None = None, pacing_state: dict | None = None) -> AuctionResult:
    """Run one auction and return the winner, the clearing price, and the trace."""
    policy = policy or {}
    frequency_state = frequency_state or {}
    pacing_state = pacing_state or {}
    floor = max(int(floor_cpm_micros), int(placement.get("floor_cpm_micros") or 0))

    trace: list[TraceEntry] = []
    eligible: list[tuple[int, str, dict]] = []

    for item in line_items:
        lid = item.get("line_item_id", "")
        ecpm = normalize_ecpm(item.get("pricing") or {}, p_ctr, p_cvr)

        if not _policy_ok(item, policy, placement, steward_policy):
            trace.append(TraceEntry(lid, ecpm, "eliminated_policy")); continue

        targeting = item.get("targeting")
        if targeting is not None:
            try:
                pred.validate(targeting)
            except pred.PredicateError:
                trace.append(TraceEntry(lid, ecpm, "eliminated_policy")); continue
            if not pred.evaluate(targeting, signal):
                trace.append(TraceEntry(lid, ecpm, "eliminated_targeting")); continue

        cap = item.get("frequency_cap") or {}
        seen = frequency_state.get(lid, 0)
        limit = cap.get("per_conversation") or cap.get("per_node_user_per_day")
        if limit is not None and seen >= limit:
            trace.append(TraceEntry(lid, ecpm, "eliminated_frequency")); continue

        pacing = item.get("pacing") or {}
        share = pacing.get("node_share_impressions")
        if share is not None and pacing_state.get(lid, 0) >= share:
            trace.append(TraceEntry(lid, ecpm, "eliminated_pacing")); continue

        if ecpm < floor:
            trace.append(TraceEntry(lid, ecpm, "eliminated_floor")); continue

        eligible.append((ecpm, lid, item))

    if not eligible:
        # No eligible bid renders nothing. The protocol has no house ads and no
        # default creative, so a no-fill is a no-fill.
        return AuctionResult(None, 0, mechanism, trace)

    # Deterministic tie-break by line_item_id so the exchange replay agrees.
    eligible.sort(key=lambda e: (-e[0], e[1]))
    (top_ecpm, top_lid, winner), rest = eligible[0], eligible[1:]

    if mechanism == "uap.auction.first_price":
        price = top_ecpm
    else:
        second = rest[0][0] if rest else 0
        price = max(second, floor) + 1

    trace.append(TraceEntry(top_lid, top_ecpm, "won"))
    trace.extend(TraceEntry(lid, ecpm, "lost") for ecpm, lid, _ in rest)
    trace.sort(key=lambda t: (OUTCOMES.index(t.outcome), t.line_item_id))
    return AuctionResult(winner, price, mechanism, trace)
