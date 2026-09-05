"""Node-side aggregate reporting (SPEC.md §6.8, Profile `uap.federated`).

§6.6 already requires reports to be aggregate, k-thresholded and noised. But the
exchange computes that aggregate from per-impression receipts it holds, so the
un-noised breakdown exists on the exchange's disk and the advertiser simply gets
a blurred view of it. The privacy guarantee is a promise about output rather
than a property of the system.

This module moves the computation to the node so the raw breakdown never exists
anywhere:

  1. The node bins its own turns against a **declared** aggregation spec.
  2. Each user contributes at most `contribution_bound` events, which is what
     bounds sensitivity and makes any DP claim meaningful.
  3. The node adds its share of the noise locally.
  4. The vector is split into additive secret shares across two independent
     aggregators. Neither one alone learns anything about any node.

The noise is distributed correctly rather than approximately. A discrete Laplace
is infinitely divisible: a geometric variable is the sum of N Pólya(1/N)
variables, so each of N nodes adding Pólya(1/N) - Pólya(1/N) makes the *sum*
exactly discrete Laplace at the target epsilon. Each node adding full local
noise would be far noisier; each node adding 1/N of the scale would not be DP at
all.

The safety property is the spec being closed. "Federated" normally means the
server ships code to run against user data, which is worse than shipping the
data, because at least data is inspectable. Here the node reads a declaration of
exactly which fields are binned, at what granularity, with what bound, and can
refuse. Same discipline as the targeting predicate language in Appendix A: no
callbacks, no regex, no network.
"""
from __future__ import annotations

import hashlib
import math
import secrets

__all__ = ["AggregationSpec", "LocalAggregator", "PrivacyBudget", "AggregationError",
           "secret_share", "reconstruct", "release", "MODULUS"]

# Shares are summed in this ring. Wide enough that a real histogram never wraps,
# small enough to stay cheap to transmit.
MODULUS = 2 ** 32

# The closed set of fields a spec may bin on. Anything else is refused, so the
# exchange cannot widen what it collects by shipping a new spec.
BINNABLE = {"intents", "commercial_intent", "locale", "surface_hint"}


class AggregationError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class AggregationSpec:
    """A declared description of what will be computed and what will leave."""

    def __init__(self, spec: dict):
        self.raw = spec
        dims = spec.get("dimensions") or []
        if not dims:
            raise AggregationError("UAP_AGG_NO_DIMENSIONS")
        for d in dims:
            if d.get("field") not in BINNABLE:
                raise AggregationError("UAP_AGG_FIELD_NOT_BINNABLE", str(d.get("field")))
            if "values" not in d and "buckets" not in d:
                raise AggregationError("UAP_AGG_OPEN_DIMENSION",
                                       f"{d['field']} declares no vocabulary; "
                                       "cardinality must be fixed in advance")
        self.dimensions = dims
        self.metrics = spec.get("metrics") or ["impressions"]
        self.contribution_bound = int(spec.get("contribution_bound", 1))
        self.epsilon = float(spec.get("epsilon", 1.0))
        self.k_floor = int(spec.get("k_floor", 50))
        self.min_participants = int(spec.get("min_participants", 1))
        if self.contribution_bound < 1:
            raise AggregationError("UAP_AGG_BAD_BOUND", "contribution_bound must be >= 1")
        if not 0 < self.epsilon <= 10:
            raise AggregationError("UAP_AGG_BAD_EPSILON", str(self.epsilon))

        self.cards = [len(d["values"]) + 1 if "values" in d else len(d["buckets"]) - 1
                      for d in dims]
        self.cells = 1
        for c in self.cards:
            self.cells *= c
        self.width = self.cells * len(self.metrics)
        if self.width > 1 << 16:
            raise AggregationError("UAP_AGG_TOO_WIDE", f"{self.width} counters")

    def cell(self, signal: dict) -> int | None:
        """Mixed-radix index of the cell this signal falls in."""
        idx = 0
        for d, card in zip(self.dimensions, self.cards):
            f = d["field"]
            if "values" in d:
                if f == "intents":
                    ids = [i.get("id", "") for i in (signal.get("intents") or [])]
                    depth = int(d.get("depth", 2))
                    got = next((v for v in d["values"]
                                if any(".".join(i.split(".")[:depth]) == v for i in ids)), None)
                else:
                    got = signal.get(f) if signal.get(f) in d["values"] else None
                # The last slot is "anything else", so a value outside the
                # declared vocabulary cannot create a new cell.
                sub = d["values"].index(got) if got is not None else card - 1
            else:
                v = signal.get(f)
                if v is None:
                    return None
                b = d["buckets"]
                sub = max(0, min(card - 1, sum(1 for t in b[1:-1] if v >= t)))
            idx = idx * card + sub
        return idx


class PrivacyBudget:
    """Epsilon spent per campaign-day, enforced by the node.

    A budget the exchange tracks is not a budget. The node refuses once it has
    spent its allowance, because the node is the only party that loses if the
    accounting is wrong.
    """

    def __init__(self, per_day: float = 1.0):
        self.per_day = per_day
        self.spent: dict[tuple[str, str], float] = {}

    def spend(self, campaign_id: str, day: str, epsilon: float) -> None:
        key = (campaign_id, day)
        used = self.spent.get(key, 0.0)
        if used + epsilon > self.per_day + 1e-9:
            raise AggregationError(
                "UAP_PRIVACY_BUDGET_EXHAUSTED",
                f"{campaign_id} on {day}: {used:.3f} spent, {epsilon:.3f} requested, "
                f"{self.per_day:.3f} allowed")
        self.spent[key] = used + epsilon

    def remaining(self, campaign_id: str, day: str) -> float:
        return self.per_day - self.spent.get((campaign_id, day), 0.0)


class LocalAggregator:
    """Bins turns locally. Nothing here is transmitted until `finalise`."""

    def __init__(self, spec: AggregationSpec):
        self.spec = spec
        self.counts = [0] * spec.width
        self._per_user: dict[str, int] = {}
        self.dropped_over_bound = 0

    def observe(self, user_key: str, signal: dict, metrics: dict | None = None) -> bool:
        """Record one turn. Returns False if the user is over their bound.

        `user_key` is a local handle. It is used to enforce the contribution
        bound and never leaves this process; without a per-user bound the
        sensitivity is unbounded and the epsilon means nothing.
        """
        seen = self._per_user.get(user_key, 0)
        if seen >= self.spec.contribution_bound:
            self.dropped_over_bound += 1
            return False
        cell = self.spec.cell(signal)
        if cell is None:
            return False
        self._per_user[user_key] = seen + 1
        metrics = metrics or {"impressions": 1}
        for m_i, name in enumerate(self.spec.metrics):
            self.counts[m_i * self.spec.cells + cell] += int(metrics.get(name, 0))
        return True

    def finalise(self, *, participants: int, rng=None) -> list[int]:
        """Add this node's share of the noise.

        Calibrated to `participants`, which the exchange publishes as a floor. If
        fewer nodes actually report, the sum is under-noised, so a node MUST use
        the declared minimum rather than a live count it cannot verify.
        """
        n = max(self.spec.min_participants, int(participants))
        # Discrete Laplace at scale sensitivity/epsilon, divided across n nodes
        # by the infinite divisibility of the geometric distribution.
        sensitivity = self.spec.contribution_bound
        p = 1.0 - math.exp(-self.spec.epsilon / sensitivity)
        return [(c + _polya(1.0 / n, p, rng) - _polya(1.0 / n, p, rng)) % MODULUS
                for c in self.counts]


def _polya(r: float, p: float, rng=None) -> int:
    """Negative binomial with real-valued r, by Gamma-Poisson mixture.

    Sum of n independent Polya(1/n, p) is Polya(1, p), which is geometric. That
    identity is what lets n nodes each add a fraction of the noise and still get
    an exactly discrete-Laplace total.
    """
    import random as _r
    rng = rng or _r
    if p >= 1.0:
        return 0
    lam = rng.gammavariate(r, (1.0 - p) / p)
    # Poisson by inversion; lam is small here so this stays cheap.
    L, k, prod = math.exp(-lam), 0, rng.random()
    while prod > L:
        k += 1
        prod *= rng.random()
    return k


def secret_share(vector: list[int], aggregators: int = 2) -> list[list[int]]:
    """Split into additive shares. Any single share is uniform noise."""
    if aggregators < 2:
        raise AggregationError("UAP_AGG_TOO_FEW_AGGREGATORS", str(aggregators))
    shares = [[secrets.randbelow(MODULUS) for _ in vector] for _ in range(aggregators - 1)]
    last = [(v - sum(s[i] for s in shares)) % MODULUS for i, v in enumerate(vector)]
    shares.append(last)
    return shares


def reconstruct(shares: list[list[int]]) -> list[int]:
    return [sum(col) % MODULUS for col in zip(*shares)]


def release(total: list[int], spec: AggregationSpec) -> list[int | None]:
    """Suppress cells below the k floor at publication.

    Noise does not hide a cell that only one node could have contributed to, so
    the k threshold is applied on the way out, not on the way in.
    """
    out: list[int | None] = []
    for v in total:
        signed = v - MODULUS if v > MODULUS // 2 else v
        out.append(signed if signed >= spec.k_floor else None)
    return out


def spec_digest(spec: dict) -> str:
    """Digest of the declared spec, so a node can prove what it agreed to."""
    from .canonical import serialize
    return "sha256:" + hashlib.sha256(serialize(spec).encode()).hexdigest()
