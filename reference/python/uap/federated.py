"""Federated ranking updates (Profile `uap.federated`, SPEC.md §6.9).

The gap this closes: a buyer writes targeting predicates blind and never learns
which contexts actually convert, because nothing that would tell them is allowed
to leave the node. Without a learning loop, relevance is capped at however good
the buyer's guess was on day one.

So the model comes to the data. A shared scorer ships inside the campaign
bundle. Each node computes a gradient on its own turns, clips each user's
contribution, adds its share of the noise, and submits additive secret shares.
The exchange averages and ships an improved scorer in the next bundle. Bundle
down, update up, better bundle down: the same rhythm the protocol already has.

Two properties do the work.

Per-user clipping is what makes the epsilon mean anything. Without a bound on
what one person can move the gradient by, sensitivity is unbounded and the noise
is decoration.

The Gaussian is stable under addition, so N nodes each adding N(0, sigma^2/N)
sum to exactly N(0, sigma^2). Each node adding the full sigma would be N times
noisier than necessary; each adding sigma/N would not be private at all.

What this is not: it is not a proof of privacy. Clipping and noise bound what a
gradient discloses, they do not eliminate it, and gradient inversion is an open
research area. The honest claim is a published epsilon, not "private".
"""
from __future__ import annotations

import math
import random

from .aggregate import MODULUS, AggregationError, AggregationSpec

__all__ = ["GradientSpec", "FederatedTrainer", "LinearScorer", "quantise",
           "dequantise", "average_updates"]

# Gradients are real-valued; secret sharing needs integers. 2^16 keeps three
# decimal places, which is far below the noise floor, so quantisation is not
# the thing limiting accuracy here.
SCALE = 1 << 16


class GradientSpec:
    """The declared description of the update a node will compute and emit."""

    def __init__(self, spec: dict, agg: AggregationSpec):
        self.model_id = spec.get("model_id") or ""
        if not self.model_id:
            raise AggregationError("UAP_FED_NO_MODEL_ID")
        self.clip_norm = float(spec.get("clip_norm", 1.0))
        self.epsilon = float(spec.get("epsilon", 1.0))
        self.delta = float(spec.get("delta", 1e-6))
        self.min_participants = int(spec.get("min_participants", 100))
        self.learning_rate = float(spec.get("learning_rate", 0.1))
        if self.clip_norm <= 0:
            raise AggregationError("UAP_FED_BAD_CLIP", str(self.clip_norm))
        if not 0 < self.epsilon <= 10:
            raise AggregationError("UAP_FED_BAD_EPSILON", str(self.epsilon))
        if not 0 < self.delta < 1:
            raise AggregationError("UAP_FED_BAD_DELTA", str(self.delta))
        # Features are the declared aggregation cells plus a bias, so the update
        # cannot see any field the aggregation spec did not already declare.
        self.dims = agg.cells + 1
        self.agg = agg

    def sigma(self) -> float:
        """Gaussian scale for the whole cohort, at L2 sensitivity = clip_norm."""
        return self.clip_norm * math.sqrt(2 * math.log(1.25 / self.delta)) / self.epsilon


class LinearScorer:
    """A logistic scorer over declared cells. Deliberately small and inspectable."""

    def __init__(self, weights: list[float]):
        self.w = list(weights)

    @classmethod
    def zeros(cls, dims: int) -> "LinearScorer":
        return cls([0.0] * dims)

    def features(self, signal: dict, agg: AggregationSpec) -> list[int]:
        cell = agg.cell(signal)
        f = [0] * (agg.cells + 1)
        f[-1] = 1                       # bias
        if cell is not None:
            f[cell] = 1
        return f

    def score(self, feats: list[int]) -> float:
        z = sum(w * x for w, x in zip(self.w, feats))
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


class FederatedTrainer:
    """Accumulates a per-user-clipped, noised gradient. Nothing leaves until emit."""

    def __init__(self, model: LinearScorer, spec: GradientSpec):
        self.model = model
        self.spec = spec
        self._by_user: dict[str, list[float]] = {}

    def observe(self, user_key: str, signal: dict, clicked: bool) -> None:
        feats = self.model.features(signal, self.spec.agg)
        err = self.model.score(feats) - (1.0 if clicked else 0.0)
        g = self._by_user.setdefault(user_key, [0.0] * self.spec.dims)
        for i, x in enumerate(feats):
            if x:
                g[i] += err * x

    def emit(self, *, participants: int, rng=None) -> list[int]:
        """Clip per user, sum, add this node's share of the noise, quantise."""
        rng = rng or random
        n = max(self.spec.min_participants, int(participants))
        total = [0.0] * self.spec.dims
        for g in self._by_user.values():
            norm = math.sqrt(sum(v * v for v in g))
            scale = min(1.0, self.spec.clip_norm / norm) if norm > 0 else 0.0
            for i, v in enumerate(g):
                total[i] += v * scale
        share_sigma = self.spec.sigma() / math.sqrt(n)
        return quantise([v + rng.gauss(0.0, share_sigma) for v in total])

    @property
    def users(self) -> int:
        return len(self._by_user)


def quantise(vec: list[float]) -> list[int]:
    return [int(round(v * SCALE)) % MODULUS for v in vec]


def dequantise(vec: list[int]) -> list[float]:
    return [((v - MODULUS) if v > MODULUS // 2 else v) / SCALE for v in vec]


def average_updates(total: list[int], participants: int, model: LinearScorer,
                    spec: GradientSpec) -> LinearScorer:
    """Apply the averaged, noised gradient. Runs on the exchange."""
    if participants < spec.min_participants:
        raise AggregationError(
            "UAP_FED_COHORT_TOO_SMALL",
            f"{participants} reported, {spec.min_participants} required; "
            "the sum is under-noised below the declared floor")
    grad = dequantise(total)
    return LinearScorer([w - spec.learning_rate * g / participants
                         for w, g in zip(model.w, grad)])
