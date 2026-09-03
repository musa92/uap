"""Targeting predicate evaluation (SPEC.md Appendix A).

A closed, total, side-effect-free boolean language over ContextSignal. No regex,
no arithmetic on user data, no external references, no callbacks.

Two properties are load-bearing:

  Fail closed. An unknown operator, a malformed term, or a missing signal field
  evaluates the containing term to False. A predicate can never widen targeting
  by being wrong.

  Bounded cost. Depth <= 8 and <= 64 terms per line item. A serving node
  evaluates 10^3 line items inside the per-turn budget, and a hostile exchange
  cannot ship a predicate that is expensive to evaluate.
"""
from __future__ import annotations

from typing import Any

MAX_DEPTH = 8
MAX_TERMS = 64

__all__ = ["evaluate", "validate", "PredicateError"]


class PredicateError(ValueError):
    """Raised by validate() for a predicate that must be rejected before use."""


def _intent_ids(signal: dict) -> set[str]:
    return {i.get("id") for i in signal.get("intents") or [] if isinstance(i, dict)}


def _confidence(signal: dict, intent_id: str) -> float | None:
    for i in signal.get("intents") or []:
        if isinstance(i, dict) and i.get("id") == intent_id:
            c = i.get("confidence")
            return c if isinstance(c, (int, float)) else None
    return None


_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _term(op: str, arg: Any, signal: dict) -> bool:
    if op == "intent_any":
        return bool(_intent_ids(signal) & set(arg)) if isinstance(arg, list) else False
    if op == "intent_all":
        return set(arg).issubset(_intent_ids(signal)) if isinstance(arg, list) else False
    if op == "intent_confidence_gte":
        if not isinstance(arg, dict):
            return False
        got = _confidence(signal, arg.get("id"))
        want = arg.get("value")
        return isinstance(got, (int, float)) and isinstance(want, (int, float)) and got >= want
    if op == "commercial_intent_gte":
        got = signal.get("commercial_intent")
        return isinstance(got, (int, float)) and isinstance(arg, (int, float)) and got >= arg
    if op == "locale_any":
        return signal.get("locale") in arg if isinstance(arg, list) else False
    if op == "geo_any":
        geo = signal.get("geo")
        return isinstance(geo, dict) and geo.get("value") in arg if isinstance(arg, list) else False
    if op == "surface_any":
        return signal.get("surface_hint") in arg if isinstance(arg, list) else False
    if op == "format_any":
        return signal.get("_format") in arg if isinstance(arg, list) else False
    if op == "turn_bucket_any":
        turn = signal.get("turn")
        return isinstance(turn, dict) and turn.get("index_bucket") in arg if isinstance(arg, list) else False
    if op == "brand_risk_max":
        safety = signal.get("safety")
        if not isinstance(safety, dict) or arg not in _RISK_ORDER:
            return False
        got = safety.get("brand_risk")
        return got in _RISK_ORDER and _RISK_ORDER[got] <= _RISK_ORDER[arg]
    return False  # unknown operator: fail closed


def evaluate(predicate: Any, signal: dict, _depth: int = 0) -> bool:
    """Evaluate `predicate` against `signal`. Never raises; never returns True by accident."""
    if _depth > MAX_DEPTH or not isinstance(predicate, dict) or len(predicate) != 1:
        return False
    (op, arg), = predicate.items()
    if op == "all":
        return isinstance(arg, list) and all(evaluate(p, signal, _depth + 1) for p in arg)
    if op == "any":
        return isinstance(arg, list) and any(evaluate(p, signal, _depth + 1) for p in arg)
    if op == "not":
        return not evaluate(arg, signal, _depth + 1)
    return _term(op, arg, signal)


def count_terms(predicate: Any, _depth: int = 0) -> int:
    if not isinstance(predicate, dict) or len(predicate) != 1:
        return 1
    (op, arg), = predicate.items()
    if op in ("all", "any") and isinstance(arg, list):
        return sum(count_terms(p, _depth + 1) for p in arg)
    if op == "not":
        return count_terms(arg, _depth + 1)
    return 1


def depth(predicate: Any) -> int:
    if not isinstance(predicate, dict) or len(predicate) != 1:
        return 0
    (op, arg), = predicate.items()
    if op in ("all", "any") and isinstance(arg, list):
        return 1 + max((depth(p) for p in arg), default=0)
    if op == "not":
        return 1 + depth(arg)
    return 1


def validate(predicate: Any) -> None:
    """Reject a predicate that exceeds the Appendix A bounds.

    Called by the node on every line item in a bundle before evaluation, so a
    hostile or buggy exchange cannot ship an unbounded predicate.
    """
    d, t = depth(predicate), count_terms(predicate)
    if d > MAX_DEPTH:
        raise PredicateError(f"predicate depth {d} exceeds {MAX_DEPTH}")
    if t > MAX_TERMS:
        raise PredicateError(f"predicate has {t} terms, exceeds {MAX_TERMS}")
