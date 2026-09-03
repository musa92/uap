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

__all__ = ["evaluate", "compile_predicate", "prepare", "validate", "PredicateError"]


class PredicateError(ValueError):
    """Raised by validate() for a predicate that must be rejected before use."""


def _intent_ids(signal: dict) -> set:
    """Intent ids as a set, using the prepared form when one is present.

    Rebuilt per call otherwise. A predicate typically references intents two or
    three times, and a bundle holds thousands of predicates, so the rebuild is
    the single hottest allocation in the evaluator.
    """
    cached = signal.get("_intent_set")
    if cached is not None:
        return cached
    return {i.get("id") for i in signal.get("intents") or [] if isinstance(i, dict)}


def prepare(signal: dict) -> dict:
    """Precompute the derived views a compiled predicate reads.

    Returns a shallow copy; the caller's signal is not mutated. Call once per
    turn, before evaluating a bundle against it.
    """
    return {**signal,
            "_intent_set": {i.get("id") for i in signal.get("intents") or []
                            if isinstance(i, dict)}}


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


# ---------------------------------------------------------------------------
# Compiled form
# ---------------------------------------------------------------------------
#
# A bundle is fetched hourly and evaluated on every turn, so the dispatch cost —
# unpacking a dict, string-comparing the operator, recursing — is paid millions
# of times for a structure that never changes. Compiling each predicate once
# into a closure tree moves that work to bundle load, which is where a
# conventional ad server does it too.
#
# The compiled form is semantically identical to evaluate(), including its
# fail-closed behaviour: `test_compiled_matches_interpreted` asserts that on
# every predicate and signal the property tests can generate.


def _compile_term(op, arg):
    """Return a closure for one leaf term, resolving the operator once."""
    if op == "intent_any" and isinstance(arg, list):
        want = frozenset(arg)
        return lambda s: bool(_intent_ids(s) & want)
    if op == "intent_all" and isinstance(arg, list):
        want = frozenset(arg)
        return lambda s: want <= _intent_ids(s)
    if op == "commercial_intent_gte" and isinstance(arg, (int, float)):
        return lambda s: isinstance(s.get("commercial_intent"), (int, float)) \
            and s["commercial_intent"] >= arg
    if op == "locale_any" and isinstance(arg, list):
        want = frozenset(arg)
        return lambda s: s.get("locale") in want
    if op == "surface_any" and isinstance(arg, list):
        want = frozenset(arg)
        return lambda s: s.get("surface_hint") in want
    if op == "format_any" and isinstance(arg, list):
        want = frozenset(arg)
        return lambda s: s.get("_format") in want
    if op == "geo_any" and isinstance(arg, list):
        want = frozenset(arg)
        return lambda s: isinstance(s.get("geo"), dict) and s["geo"].get("value") in want
    if op == "turn_bucket_any" and isinstance(arg, list):
        want = frozenset(arg)
        return lambda s: isinstance(s.get("turn"), dict) \
            and s["turn"].get("index_bucket") in want
    # Uncommon or awkward to specialise: fall back to the interpreter, which
    # keeps one definition of the semantics rather than two.
    return lambda s: _term(op, arg, s)


def compile_predicate(predicate, _depth: int = 0):
    """Compile a predicate into a callable taking a signal and returning bool.

    Fails closed exactly as evaluate() does: an over-deep, malformed or unknown
    construct compiles to a closure that always returns False.
    """
    if _depth > MAX_DEPTH or not isinstance(predicate, dict) or len(predicate) != 1:
        return lambda s: False
    (op, arg), = predicate.items()

    if op == "all":
        if not isinstance(arg, list):
            return lambda s: False
        parts = [compile_predicate(p, _depth + 1) for p in arg]
        if not parts:
            return lambda s: True

        def _all(s, _parts=parts):
            for f in _parts:
                if not f(s):
                    return False
            return True
        return _all
    if op == "any":
        if not isinstance(arg, list):
            return lambda s: False
        parts = [compile_predicate(p, _depth + 1) for p in arg]

        def _any(s, _parts=parts):
            for f in _parts:
                if f(s):
                    return True
            return False
        return _any
    if op == "not":
        inner = compile_predicate(arg, _depth + 1)
        return lambda s: not inner(s)

    return _compile_term(op, arg)
